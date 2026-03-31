import { z } from "zod";

// Este es el esquema para cada item dentro del array 'payload'
// ESTA exportación es la que necesita app.js
export const payloadItemSchema = z.object({
  timestamp: z.string().datetime(), // ISO 8601 obligatorio
  battery: z.number().int().optional(),
  temperature: z.number().optional(),
  humidity: z.number().optional(),
  water_conv: z.number().optional(),
  pulse_conv: z.number().optional(),
  water: z.number().optional(),
}).passthrough(); // acepta campos extra que no estén definidos

// Este es el esquema principal del body que llega a /sensors/data
// Y ESTA es la exportación principal que te da el error
export const ingestSchema = z.object({
  deviceType: z.string(),
  serialNumber: z.string(),
  id: z.string(),
  payload: z.array(payloadItemSchema).min(1), // Debe tener al menos 1 item
});

