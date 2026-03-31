import express from "express";
import helmet from "helmet";
import morgan from "morgan";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { config } from "./config.js";
import { ingestSchema } from "./schema.js";

const app = express();
app.use(helmet());
app.use(express.json({ limit: "1mb" }));
app.use(morgan("combined"));

// --- CONFIGURACIÓN DE RUTAS ---
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DATA_DIR = path.join(__dirname, "..", "data");
const DATA_FILE = path.join(DATA_DIR, "piscina.json");

// --- FUNCIONES DE PERSISTENCIA ---

/**
 * Cargar datos desde archivo JSON al arrancar
 */
function loadData() {
  try {
    if (fs.existsSync(DATA_FILE)) {
      const raw = fs.readFileSync(DATA_FILE, "utf8");
      const data = JSON.parse(raw);
      console.log("✅ Datos cargados desde archivo:", DATA_FILE);
      console.log(`📊 Último dato: ${data.ultimo_dato || "ninguno"}`);
      return data;
    }
  } catch (e) {
    console.error("⚠️ Error cargando datos, usando valores por defecto:", e.message);
  }
  
  // Valores por defecto si no existe archivo o hay error
  return {
    ph: null,
    cloro_libre: null,
    cloro_total: null,
    turbidez: null,
    temp: null,
    ultimo_dato: null,
    serial_device: null
  };
}

/**
 * Guardar datos en archivo JSON
 */
function saveData(data) {
  try {
    // Crear directorio si no existe
    if (!fs.existsSync(DATA_DIR)) {
      fs.mkdirSync(DATA_DIR, { recursive: true });
      console.log("📁 Directorio creado:", DATA_DIR);
    }
    
    fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2), "utf8");
    console.log("💾 Datos guardados en:", DATA_FILE);
  } catch (e) {
    console.error("❌ Error guardando datos:", e.message);
  }
}

// --- VARIABLE EN MEMORIA (cargada desde archivo) ---
let datosPiscina = loadData();

// --- RUTA DE HEALTHCHECK (PÚBLICA) ---
app.get("/health", (_req, res) => res.json({ 
  status: "ok",
  ultimo_dato: datosPiscina.ultimo_dato,
  data_file: DATA_FILE
}));

// --- MIDDLEWARE DE SEGURIDAD (API KEY) ---
app.use((req, res, next) => {
  const key = req.header("x-api-key");
  if (!key || key !== config.apiKey) {
    return res.status(401).json({ error: "No autorizado (API Key inválida)" });
  }
  next();
});

// --- RUTAS PROTEGIDAS ---

// 1. ENDPOINT DE RECEPCIÓN (Webhook Global Omnium)
app.post("/webhooks/piscina", (req, res) => {
  const body = req.body;
  
  // Validación básica del formato Global Omnium
  if (!body.payload || !Array.isArray(body.payload) || body.payload.length === 0) {
    console.error("❌ Formato incorrecto recibido:", JSON.stringify(body));
    return res.status(400).json({ error: "Formato JSON inválido. Se espera array 'payload'." });
  }
  
  // Tomamos la ÚLTIMA medida del array (la más reciente)
  const ultimaMedida = body.payload[body.payload.length - 1];
  
  // Actualizamos la memoria
  datosPiscina.serial_device = body.serialNumber;
  datosPiscina.ultimo_dato = ultimaMedida.timestamp;
  
  // Mapeo flexible de campos
  if (ultimaMedida.temperature !== undefined) datosPiscina.temp = ultimaMedida.temperature;
  if (ultimaMedida.ph !== undefined) datosPiscina.ph = ultimaMedida.ph;
  if (ultimaMedida.chlorine !== undefined) datosPiscina.cloro_libre = ultimaMedida.chlorine;
  if (ultimaMedida.chlorineTotal !== undefined) datosPiscina.cloro_total = ultimaMedida.chlorineTotal;
  if (ultimaMedida.turbidity !== undefined) datosPiscina.turbidez = ultimaMedida.turbidity;
  
  // ✅ NUEVO: Guardar en archivo para persistencia
  saveData(datosPiscina);
  
  // Log para depuración
  console.log(`✅ Datos actualizados de ${body.deviceType} (${body.serialNumber})`);
  console.log(`📊 pH: ${datosPiscina.ph}, Temp: ${datosPiscina.temp}°C, Cloro: ${datosPiscina.cloro_libre}`);
  console.log(`📅 Timestamp: ${datosPiscina.ultimo_dato}`);
  
  return res.status(200).json({ status: "ok", message: "Datos procesados y guardados correctamente" });
});

// 2. ENDPOINT DE LECTURA (Para tu Dashboard Local)
app.get("/piscina", (_req, res) => {
  res.json(datosPiscina);
});

// 3. RUTA ORIGINAL DE SENSORES (compatibilidad)
app.post("/sensors/data", (req, res) => {
  const parsed = ingestSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: "Payload inválido", details: parsed.error.flatten() });
  }
  console.log(`Datos recibidos de: ${parsed.data.serialNumber}`);
  return res.json({ status: "ok", received: parsed.data.payload.length });
});

// Manejo de errores
app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ error: "Error interno del servidor" });
});

app.listen(config.port, () => {
  console.log(`🚀 API Segura escuchando en http://0.0.0.0:${config.port}`);
  console.log(`💾 Persistencia activada en: ${DATA_FILE}`);
  console.log(`📊 Datos actuales: pH=${datosPiscina.ph}, Temp=${datosPiscina.temp}`);
});
