# Plan: llamadas salientes con agente de voz IA (Telnyx, Chile)

> **Estado (2026-10-26):** implementado. Verificación 0–2 completada (tests, `--dry-run`, `setup-assistant`). Pendiente: la llamada real de prueba (paso 3) y la prueba de no contestar (paso 4).

## Contexto
Proyecto vacío (`voice-assistance-outbound/v1`). Se necesita un script que, por cada fila de `llamadas.csv`, llame a un centro médico con un agente de voz IA de Telnyx. El agente consulta por un examen en nombre de un paciente, sin inventar datos ni agendar horas. El resultado de cada llamada se agrega como una fila a `consolidado.csv`.

## Enfoque
Usamos **Telnyx AI Assistants** para no armar STT/LLM/TTS propios. El flujo usa solo polling, sin webhooks, así que no hace falta ngrok ni un servidor público. Todo corre con una sola credencial (`TELNYX_API_KEY`).

1. **Asistente** (una vez): `setup_assistant.py` crea el asistente con `POST /v2/ai/assistants` y deja su ID en `.env`. El asistente usa:
   - Prompt en español chileno con variables dinámicas `{{nombre_paciente}}`, `{{examen}}`, `{{prevision}}`, `{{centro_medico}}`, `{{ciudad}}` y `{{saludo}}`. El script calcula `saludo` ("buenos días" o "buenas tardes") según la hora de Chile.
   - **Estilo de la conversación**, natural y por turnos, como una persona llamando:
     - **Apertura:** "Hola, {{saludo}}, ¿hablo con {{centro_medico}}?". Espera la confirmación.
     - **Presentación:** se identifica en una frase corta como asistente virtual que consulta por {{nombre_paciente}}. Ejemplo: "Le hablo de parte de {{nombre_paciente}}, soy un asistente virtual".
     - **Pregunta inicial:** "Quisiera saber si ustedes realizan {{examen}}".
     - **Una pregunta por turno.** Espera la respuesta antes de seguir y nunca suelta la lista completa.
     - **Repreguntas del centro:** las responde con los datos de la fila. Ciudad: {{ciudad}}. Previsión ("¿Fonasa o Isapre?"): {{prevision}}. Si le preguntan algo que no sabe (RUT, edad, etc.), responde que no tiene ese dato y continúa.
     - **Esperas:** si le dicen "déjeme revisar", espera en silencio sin interrumpir.
     - **Orden aproximado:** si lo realizan → valor → acepta {{prevision}} (si no salió ya) → disponibilidad → preparación → orden médica. No repite lo que el centro ya respondió.
     - **Cierre:** "Ok, perfecto, muchas gracias" y cuelga con la herramienta `hangup`.
     - **Si no realizan el examen:** agradece y cierra de inmediato.
     - **Siempre:** frases cortas, tono cordial, nunca inventa datos y nunca agenda horas (si le ofrecen agendar, dice que el paciente se comunicará directamente).
     - **Derivaciones:** si lo derivan a otro canal (web, WhatsApp, otro número), lo anota y cierra cortésmente.
     - **Buzón de voz o IVR sin salida:** cuelga.
   - Voz en español y la herramienta `hangup` activada. El agente espera que el centro hable primero y luego saluda, en vez de un saludo largo grabado.
2. **Llamada** (por fila): `POST /v2/texml/ai_calls/{TELNYX_TEXML_APP_ID}` con `From`, `To=telefono_centro`, `AIAssistantId` y `AIAssistantDynamicVariables` (la fila del CSV).
3. **Esperar fin**: polling del estado de la llamada (con el SID o `call_control_id` que devuelva la respuesta) hasta que termine. Tiene un timeout máximo configurable (p. ej. 10 min). El estado de Telnyx se traduce a `estado_llamada`: `completada`, `no contesta`, `ocupado`, `fallida` o `timeout`.
4. **Transcripción**: `GET /v2/ai/conversations?metadata->call_control_id=eq.<id>` y luego `GET /v2/ai/conversations/{id}/messages`.
5. **Extracción**: `POST /v2/ai/chat/completions`, el LLM de Telnyx compatible con OpenAI, con salida JSON estricta. Las instrucciones son extraer solo lo que dijo el centro y usar `"no informado"` cuando falte algo. Además genera un `resumen` breve. Si no hubo conversación, todos los campos quedan en "no informado" y el resumen explica el estado.
6. **Consolidado**: se agrega la fila a `consolidado.csv` apenas termina cada llamada. La cabecera se escribe solo si el archivo no existe, en UTF-8 con BOM para que Excel lo abra bien. Las llamadas son **secuenciales** y tienen una pausa configurable entre ellas.

Si una llamada falla (error HTTP, timeout, etc.), igual se escribe su fila con `estado_llamada=error: <motivo>` y el script sigue con la siguiente.

## Estructura del proyecto
Es un paquete Python instalable (`src/` layout, Python ≥3.11) organizado en capas. El dominio no depende de Telnyx ni de CSV. Las integraciones se acceden a través de interfaces (`Protocol`), así que mañana se puede cambiar de proveedor de voz, guardar en BD o Google Sheets, o agregar otro tipo de campaña sin tocar la orquestación.

```
v1/
├── pyproject.toml            # deps: httpx, pydantic, pydantic-settings, typer; dev: pytest, respx, ruff
├── README.md
├── .env.example
├── .mcp.json                 # MCP remoto de Telnyx para Claude Code (clave vía ${TELNYX_API_KEY})
├── .gitignore                # .env, consolidado.csv, __pycache__, .venv
├── data/
│   └── llamadas.ejemplo.csv
├── prompts/
│   ├── agente_consulta_examen.md   # instrucciones del agente de voz (plantilla)
│   └── extraccion.md               # instrucciones para extraer datos de la transcripción
├── src/voice_outbound/
│   ├── __init__.py
│   ├── config.py             # Settings (pydantic-settings) leídas desde .env, validadas al arrancar
│   ├── logging.py            # logging estructurado (un logger por módulo)
│   ├── domain/
│   │   ├── models.py         # SolicitudLlamada, ResultadoLlamada, DatosConsulta, EstadoLlamada (Enum)
│   │   └── ports.py          # Protocols: VoiceProvider, TranscriptProvider, Extractor, ResultRepository, RequestSource
│   ├── integrations/telnyx/
│   │   ├── client.py         # TelnyxClient: httpx con auth, timeouts, reintentos con backoff, errores tipados
│   │   ├── calls.py          # TelnyxVoiceProvider: iniciar ai_call, consultar estado → EstadoLlamada
│   │   ├── conversations.py  # TelnyxTranscriptProvider: conversación y mensajes por call_control_id
│   │   ├── assistants.py     # crear/actualizar asistente desde prompts/
│   │   └── inference.py      # TelnyxExtractor: chat/completions con JSON → DatosConsulta
│   ├── io/
│   │   ├── csv_source.py     # lee y valida llamadas.csv (E.164 +56, columnas, ciudad opcional)
│   │   └── csv_repository.py # append a consolidado.csv (cabecera si no existe, UTF-8 BOM, flush por fila)
│   ├── services/
│   │   ├── prompts.py        # carga plantillas y arma variables dinámicas (saludo según hora America/Santiago)
│   │   └── campaign.py       # CampaignRunner: por cada solicitud → llamar → esperar → transcribir → extraer → guardar;
│   │                         #   aísla errores por fila; pausa y límite configurables
│   └── cli.py                # Typer: `voice-outbound run [--csv] [--salida] [--limite] [--dry-run]`
│                             #        `voice-outbound setup-assistant`
└── tests/
    ├── conftest.py           # fakes de los ports
    ├── test_csv_source.py
    ├── test_csv_repository.py
    ├── test_campaign.py      # flujo completo con fakes: completada, no contesta, error → fila "no informado"
    ├── test_prompts.py       # saludo días/tardes, render de variables
    └── test_telnyx_calls.py  # mapeo de estados y parseo de respuestas con respx (HTTP mockeado)
```

**Principios aplicados**
- **Inyección de dependencias:** `cli.py` es el único lugar que arma las implementaciones concretas (composition root). `CampaignRunner` recibe solo los ports, lo que lo hace testeable sin red.
- **Modelos tipados con pydantic:** `DatosConsulta` declara los campos de salida con default `"no informado"`. Así el esquema del CSV y el JSON de extracción salen de una sola fuente.
- **Prompts fuera del código:** viven en `prompts/` para editarlos sin tocar Python.
- **Configuración centralizada y validada:** si falta una variable obligatoria, el programa falla rápido con un mensaje claro.
- **Errores tipados:** `TelnyxError`, `CallTimeoutError` y similares. Ninguna fila se pierde: un fallo produce una fila con `estado_llamada=error`.
- **Extensibilidad prevista:** las llamadas en paralelo serían otro runner con semáforo, y los webhooks en lugar de polling, otro `VoiceProvider`. No implemento estas extensiones ahora, pero el diseño las permite.

**`.env.example`**
- `TELNYX_API_KEY`
- `TELNYX_TEXML_APP_ID`
- `TELNYX_FROM_NUMBER` (+56)
- `TELNYX_ASSISTANT_ID`
- `TELNYX_EXTRACTION_MODEL`
- `MAX_DURACION_SEG`
- `PAUSA_ENTRE_LLAMADAS_SEG`
- `CIUDAD_DEFAULT`

**CSV de entrada:** las columnas del enunciado más una columna opcional `ciudad`, que se completa con `CIUDAD_DEFAULT` si falta.

**README breve:**
- Requisitos en el portal de Telnyx: número +56, TeXML App y perfil de voz saliente con Chile habilitado.
- Instalación con `pip install -e .`.
- `setup-assistant`, `run` y formato de los CSV.
- Mapa rápido de la arquitectura.

## Skills de Telnyx (paso 0 de la implementación)
Antes de escribir código, se instalan las skills oficiales de Telnyx para Claude Code. Así la implementación usa la referencia actualizada de la API en lugar de suposiciones. El repositorio correcto es `team-telnyx/ai`. Las skills siguen el formato `<producto>-python` porque el proyecto es Python.

**Núcleo: las usa el código del proyecto**

| Skill | Para qué se usa en el plan | Módulos |
|---|---|---|
| `telnyx-ai-assistants-python` | Crear/actualizar el asistente (prompt, voz, `hangup`, variables dinámicas) y leer conversaciones y mensajes | `integrations/telnyx/assistants.py`, `conversations.py` |
| `telnyx-texml-python` | Iniciar la llamada con `POST /v2/texml/ai_calls/{app_id}` y consultar su estado (SID, `Status`: completed, busy, no-answer, failed) | `integrations/telnyx/calls.py` |
| `telnyx-ai-inference-python` | Extraer datos de la transcripción con `chat/completions` y salida JSON | `integrations/telnyx/inference.py` |
| `telnyx-voice-python` | Call Control: estado de la llamada por `call_control_id` y colgado forzado si se supera `MAX_DURACION_SEG` | `integrations/telnyx/calls.py` |

**Setup de la cuenta: se usan para configurar Telnyx y documentarlo en el README, no en el código de runtime**

| Skill | Para qué |
|---|---|
| `telnyx-sip-python` | Perfil de voz saliente con destinos Chile (CL) habilitados |
| `telnyx-numbers-python` | Buscar y comprar el número chileno +56 (`TELNYX_FROM_NUMBER`) |
| `telnyx-numbers-compliance-python` | Requisitos regulatorios para números de Chile, si Telnyx los exige |

```bash
# Núcleo
npx skills add team-telnyx/ai --skill telnyx-ai-assistants-python --agent claude-code
npx skills add team-telnyx/ai --skill telnyx-texml-python          --agent claude-code
npx skills add team-telnyx/ai --skill telnyx-ai-inference-python   --agent claude-code
npx skills add team-telnyx/ai --skill telnyx-voice-python          --agent claude-code
# Setup de cuenta
npx skills add team-telnyx/ai --skill telnyx-sip-python                --agent claude-code
npx skills add team-telnyx/ai --skill telnyx-numbers-python            --agent claude-code
npx skills add team-telnyx/ai --skill telnyx-numbers-compliance-python --agent claude-code
```

No se incluyen otras skills de voz (gather, media, streaming, conferencing, advanced) porque la conversación la maneja el AI Assistant, sin STT/TTS propio. Tampoco messaging ni webrtc, porque están fuera del alcance. Si se agregan funcionalidades, por ejemplo WhatsApp/SMS de seguimiento o webhooks en vez de polling, se suma la skill correspondiente.

## MCP de Telnyx (paso 0, junto con las skills)
Las skills aportan la referencia de la API, y el MCP permite que Claude Code **consulte y opere la cuenta real de Telnyx** mientras se desarrolla. Se usa el servidor remoto oficial `https://api.telnyx.com/v2/mcp`, configurado a nivel de proyecto en `.mcp.json` para que quede versionado junto al código **sin la clave**:

```json
{
  "mcpServers": {
    "telnyx": {
      "type": "http",
      "url": "https://api.telnyx.com/v2/mcp",
      "headers": { "Authorization": "Bearer ${TELNYX_API_KEY}" }
    }
  }
}
```

- Claude Code expande `${TELNYX_API_KEY}` desde el entorno del shell, y **no lee el `.env` del proyecto**. Por eso hay que exportar la variable antes de abrir `claude`, por ejemplo con `set -a; source .env; set +a`.
- No usar `claude mcp add ... --header "Authorization: Bearer $TELNYX_API_KEY"`: el shell expandiría la clave y quedaría escrita en texto plano en `.mcp.json`.
- La alternativa local, si el remoto falla, es `npx -y @telnyx/mcp --api-key=...`. Pasaría por `env` del `.mcp.json`, nunca con la clave literal.
- Verificar con `/mcp` dentro de Claude Code que el servidor `telnyx` aparezca conectado.

**Para qué se usa:** solo en desarrollo y setup. El script en runtime sigue usando `TelnyxClient`.
- **Setup de cuenta:** comprobar que el número +56 esté activo, que la TeXML App apunte al perfil de voz saliente y que Chile esté habilitado. Así se obtienen `TELNYX_TEXML_APP_ID` y `TELNYX_FROM_NUMBER` sin entrar al portal.
- **Asistente:** después de `setup-assistant`, revisar su configuración real (voz, herramientas, variables).
- **Depuración:** tras la llamada de prueba, consultar la conversación y los mensajes para confirmar la forma real de la respuesta de `ai_calls` y del estado de la llamada (ver Riesgos) antes de fijar el parseo y los tests con `respx`.
- **Precaución:** el MCP puede ejecutar acciones con costo, como comprar números o hacer llamadas. Esas acciones requieren confirmación explícita del usuario.

No se instala el plugin `/plugin install telnyx-...@telnyx` porque duplicaría las skills ya instaladas con `npx skills add`.

Se agrega `.mcp.json` a la raíz del proyecto y una sección corta en el README sobre cómo exportar la clave y verificar con `/mcp`.

## Riesgos y cosas a confirmar al implementar
- La forma exacta de la respuesta de `ai_calls` (nombre del ID de llamada) y el endpoint de estado. Lo primero es revisarlo en las skills `telnyx-texml-python` y `telnyx-ai-assistants-python`. Después lo confirmo con una llamada a un número propio y ajusto el parseo.
- Si las skills muestran que el SDK oficial `telnyx` para Python cubre estos endpoints (ai_calls, assistants, conversations, inference), evaluar usarlo dentro de `TelnyxClient` en lugar de `httpx` directo. La interfaz de los ports no cambia.
- Chile exige que el perfil de voz saliente tenga destinos CL habilitados. Esto va documentado en el README.
- Validar los teléfonos en formato E.164 `+56…` antes de llamar.

## Verificación
0. `pytest` y `ruff check` en verde.
1. `voice-outbound run --dry-run`: valida el CSV y muestra las variables por fila.
2. `voice-outbound setup-assistant`: el asistente queda visible en el portal.
3. Llamada real a **tu propio celular** (una fila en `llamadas.csv`): haces de centro médico, respondes algunas preguntas y omites otras. Revisar que `consolidado.csv` tenga los datos correctos y "no informado" donde corresponde.
4. Probar no contestar o rechazar la llamada y revisar que `estado_llamada` lo refleje.
