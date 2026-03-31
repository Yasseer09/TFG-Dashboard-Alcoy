# 🏊 Dashboard IoT - Smart City Alcoy

Dashboard de monitorización en tiempo real para instalaciones deportivas municipales del Ayuntamiento de Alcoy, desarrollado como Trabajo de Fin de Grado (TFG) en la Universitat Politècnica de València (EPSA - Campus Alcoy).

## 📋 Descripción

Sistema IoT que integra múltiples fuentes de datos para la monitorización centralizada de instalaciones deportivas municipales:

- **Calidad del aire** (PM10, PM2.5, NO₂, O₃)
- **Niveles de CO₂** en espacios cerrados
- **Temperatura y humedad** ambiental
- **Parámetros de piscinas** (pH, cloro, temperatura) - Integración con Global Omnium
- **Aforo** en tiempo real
- **Consumo energético**

## 🏗️ Arquitectura

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  APIs Externas  │────▶│   VPS (Node.js) │────▶│   Raspberry Pi  │
│  Global Omnium  │     │   Webhooks      │     │   Dashboard     │
│  Ayto. Alcoy    │     │   Puerto 8080   │     │   Flask :5000   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

- **api-webhooks/** - Backend Node.js que recibe webhooks de sensores (VPS)
- **dashboard/** - Frontend Flask desplegado en Raspberry Pi (modo kiosko)

## 🛠️ Tecnologías

| Componente | Tecnología |
|------------|------------|
| Backend Webhooks | Node.js + Express |
| Dashboard | Python + Flask |
| Frontend | HTML5, CSS3, JavaScript |
| Visualización | Chart.js |
| Hardware | Raspberry Pi 4 |
| Proxy inverso | Caddy + Let's Encrypt |
| DNS dinámico | DuckDNS |

## 📁 Estructura del proyecto

```
TFG-Dashboard-Alcoy/
├── api-webhooks/          # Backend Node.js (VPS)
│   ├── src/               # Código fuente
│   └── package.json       # Dependencias
│
├── dashboard/             # Dashboard Flask (Raspberry Pi)
│   ├── main.py            # Aplicación principal
│   ├── static/            # CSS, JS, imágenes
│   ├── templates/         # Plantillas HTML
│   ├── config.json        # Configuración
│   └── requirements.txt   # Dependencias Python
│
└── README.md
```

## 🚀 Despliegue

### API Webhooks (VPS)

```bash
cd api-webhooks
npm install
npm start
```

### Dashboard (Raspberry Pi)

```bash
cd dashboard
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 🔗 Demo en producción

- **Dashboard:** [alcoy-smartcity.duckdns.org](https://alcoy-smartcity.duckdns.org)
- **Endpoint webhooks:** `https://alcoy-smartcity.duckdns.org/webhooks/piscina`

## 👥 Colaboradores

Proyecto desarrollado en colaboración con:
- **Ayuntamiento de Alcoy** - Departamento Smart City
- **Global Omnium** - Integración de sensores de piscinas

## 📄 Licencia

Proyecto académico - TFG Universitat Politècnica de València (2025-2026)

## 👤 Autor

**Yasser Semlali**  
Grado en Ingeniería Informática - EPSA Campus Alcoy  
Universitat Politècnica de València
