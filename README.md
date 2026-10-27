# voice-outbound

Por cada fila de `llamadas.csv`, llama a un centro médico con un agente de voz IA de Telnyx. El agente consulta por un examen en nombre de un paciente, sin inventar datos ni agendar horas. El resultado de cada llamada se agrega como una fila a `consolidado.csv`.

Solo usa polling, así que no necesita webhooks, ngrok ni un servidor público. Basta con `TELNYX_API_KEY`.

## Requisitos en Telnyx
- Un número chileno `+56` activo (`TELNYX_FROM_NUMBER`).
- Un perfil de voz saliente (Outbound Voice Profile) con el destino **CL** habilitado y asociado a la TeXML App del asistente.
- Saldo suficiente: cada llamada cobra el minuto saliente a Chile, más el asistente y la inferencia.

La TeXML App la crea Telnyx automáticamente al crear el asistente (`setup-assistant` deja su ID en `.env`). Revisa en el portal que esté asociada al perfil de voz saliente con Chile habilitado.

## Instalación
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # y completa TELNYX_FROM_NUMBER
```
`TELNYX_API_KEY` puede ir en `.env` o venir exportada desde el shell (p. ej. `~/.zshenv`).

## Uso
```bash
voice-outbound setup-assistant          # crea o actualiza el asistente desde prompts/
voice-outbound run --dry-run            # valida data/llamadas.csv y muestra las variables por fila
voice-outbound run --csv data/llamadas.csv --salida consolidado.csv [--limite 1]
```

### `data/llamadas.csv`
| columna | obligatoria | ejemplo |
|---|---|---|
| `nombre_paciente` | sí | María González |
| `examen` | sí | resonancia magnética de rodilla |
| `prevision` | sí | Fonasa |
| `centro_medico` | sí | Clínica Ejemplo |
| `telefono_centro` | sí | +56222222222 (E.164; se aceptan espacios y guiones) |
| `ciudad` | no | si viene vacía se usa `CIUDAD_DEFAULT` |

Ver `data/llamadas.ejemplo.csv`. El archivo completo se valida antes de hacer la primera llamada.

### `consolidado.csv`
UTF-8 con BOM, para que Excel lo abra bien. Cada llamada agrega una fila apenas termina, con estas columnas:

`fecha_hora`, las columnas de entrada, `estado_llamada` (`completada`, `no contesta`, `ocupado`, `fallida`, `timeout` o `error: <motivo>`), `realiza_examen`, `valor`, `acepta_prevision`, `disponibilidad`, `preparacion`, `requiere_orden_medica`, `derivacion`, `resumen` y `call_id`.

Si el centro no informó un dato, la columna queda en `no informado`.

## Arquitectura
```
cli.py (composition root)
  └─ services/campaign.py   CampaignRunner: llamar → esperar → transcribir → extraer → guardar
       usa solo los ports de domain/ports.py:
       VoiceProvider       → integrations/telnyx/calls.py          POST /texml/ai_calls, GET /texml/Accounts/{sid}/Calls/{sid}
       TranscriptProvider  → integrations/telnyx/conversations.py  GET /ai/conversations, …/messages
       Extractor           → integrations/telnyx/inference.py      POST /ai/chat/completions (JSON)
       RequestSource       → io/csv_source.py
       ResultRepository    → io/csv_repository.py
```
- Los prompts viven en `prompts/` y se pueden editar sin tocar Python. Después de editar `agente_consulta_examen.md`, corre `setup-assistant` de nuevo.
- Para cambiar de proveedor, o guardar en una BD o Google Sheets, basta con otra implementación del port correspondiente.

## Desarrollo
```bash
pytest && ruff check .
```

### MCP de Telnyx en Claude Code
`.mcp.json` configura el MCP remoto `https://api.telnyx.com/v2/mcp` con `${TELNYX_API_KEY}`. Claude Code toma esa variable del entorno del shell, **no** del `.env`. Exporta la clave antes de abrir `claude` (o déjala en `~/.zshenv`) y verifica con `/mcp` que `telnyx` aparezca conectado. Ojo: el MCP puede ejecutar acciones con costo.
