import dotenv from "dotenv";
// Carga las variables de entorno desde el archivo .env
// (Asegúrate que .env está en la raíz, junto a package.json)
dotenv.config();

// Exportación NOMBRADA 'config'
// ESTA es la línea clave que corrige el error
export const config = {
  port: process.env.PORT || 8080,
  apiKey: process.env.API_KEY || "cambia-esta-clave",
  env: process.env.NODE_ENV || "development",
  logLevel: process.env.LOG_LEVEL || "info",
};

