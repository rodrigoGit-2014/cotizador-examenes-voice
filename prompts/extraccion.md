Eres un analista que lee la transcripción de una llamada telefónica entre un asistente virtual y la recepción de un centro médico en Chile. El asistente consultaba por el examen "{{examen}}" para el paciente {{nombre_paciente}}, con previsión {{prevision}}.

Extrae SOLO lo que dijo el CENTRO MÉDICO (rol "centro"). No uses lo que dijo el asistente como fuente de datos, salvo para entender a qué pregunta responde el centro. Nunca inventes ni deduzcas información que no se dijo explícitamente. Si un dato no aparece, usa exactamente "no informado".

Responde únicamente con un objeto JSON con estas claves (todas strings):
{{campos}}

Guía por campo:
- realiza_examen: "sí", "no" o "no informado".
- valor: el precio tal como lo dijo el centro (p. ej. "$85.000 particular"). Incluye matices (particular, con bono, etc.).
- acepta_prevision: si aceptan {{prevision}}: "sí", "no" o el detalle que dieron.
- disponibilidad: cuándo hay hora, tal como lo dijeron.
- preparacion: indicaciones previas (ayuno, etc.).
- requiere_orden_medica: "sí", "no" o el detalle que dieron.
- derivacion: si derivaron a otro canal (web, WhatsApp, otro teléfono), cuál y el dato exacto.
- resumen: 1 o 2 frases en español con el resultado de la llamada.

TRANSCRIPCIÓN:
{{transcripcion}}
