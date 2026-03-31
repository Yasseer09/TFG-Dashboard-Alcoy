class DashboardApp {
    constructor() {
        // Configuración centralizada
        this.config = {
            dataUpdateInterval: 5 * 60 * 1000, // 5 minutos
            maxRetries: 3,
            retryDelay: 2000,
            capacities: {
                total_complejo: 200,
                sala_gimnasio: 50
            },
            thresholds: {
                co2: { good: 800, warning: 1000 },
                ph: { low: 7.2, high: 7.6 }
            }
        };

        // Estado de la aplicación
        this.state = {
            slides: [],
            currentSlideIdx: 0,
            currentTimeout: null,
            charts: {},
            isOnline: navigator.onLine
        };

        // Referencias a elementos del DOM
        this.elements = {};
       
        // Iniciar la aplicación
        this.init();
    }

    async init() {
        try {
            this.cacheElements();
            this.setupEventListeners();
            this.startClock();
            await this.loadConfiguration();
            await this.updateData();
            this.startDataUpdateLoop();
            console.log('✅ Dashboard inicializado correctamente');
        } catch (error) {
            this.handleError('Error fatal durante la inicialización', error);
            this.showNotification('Error grave al iniciar. Por favor, recargue.', 'danger');
        }
    }

    cacheElements() {
        const ids = [
            'nav-clock', 'slides-container', 'chartAir', 'peopleTotalValue',
            'peopleGymValue', 'peopleTotalProgress', 'peopleGymProgress', 'co2Value',
            'co2Time', 'co2Status', 'tempValue', 'humValue', 'chartSolar',
            'solarRatioValue', 'poolPhValue', 'poolTempValue', 'poolCloroLibreValue',
            'poolCloroTotalValue', 'poolCloroResidualValue', 'poolTurbidezValue',
            'peopleTotalCapacity', 'peopleGymCapacity'
        ];
        ids.forEach(id => this.elements[id] = document.getElementById(id));
    }

    setupEventListeners() {
        window.addEventListener('online', () => this.handleConnectionChange(true));
        window.addEventListener('offline', () => this.handleConnectionChange(false));
    }

    handleConnectionChange(isOnline) {
        this.state.isOnline = isOnline;
        if (isOnline) {
            this.showNotification('Conexión restaurada', 'success');
            this.updateData();
        } else {
            this.showNotification('Sin conexión. Mostrando últimos datos.', 'warning');
        }
    }

    startClock() {
        if (!this.elements['nav-clock']) return;
        const update = () => {
            this.elements['nav-clock'].textContent = new Date().toLocaleString('es-ES', {
                year: 'numeric', month: '2-digit', day: '2-digit',
                hour: '2-digit', minute: '2-digit', second: '2-digit'
            });
        };
        update();
        setInterval(update, 1000);
    }
   
    async loadConfiguration() {
        try {
            const response = await fetch('/config');
            if (!response.ok) throw new Error('No se pudo cargar config');
            const config = await response.json();
           
            // Actualizar capacidad en cabeceras si existen los elementos
            if (this.elements.peopleTotalCapacity) {
                this.elements.peopleTotalCapacity.textContent = `Cap: ${this.config.capacities.total_complejo}`;
            }
            if (this.elements.peopleGymCapacity) {
                this.elements.peopleGymCapacity.textContent = `Cap: ${this.config.capacities.sala_gimnasio}`;
            }
           
            // Crear slides basados en la configuración
            this.state.slides = [];
            const enabledSlides = config.slides.filter(s => s.enabled);
           
            for (const slide of enabledSlides) {
                if (slide.type === 'video') {
                    this.createVideoSlide(slide);
                    this.state.slides.push({
                        id: `slide_video_${slide.id}`,
                        type: 'video',
                        filename: slide.filename
                    });
                } else if (slide.type === 'data') {
                    this.state.slides.push({
                        id: 'slide_data_panel',
                        type: 'data',
                        duration: slide.duration || 30
                    });
                }
            }

            console.log('📋 Slides configurados:', this.state.slides);

            // Iniciar carrusel si hay slides
            if (this.state.slides.length > 0) {
                this.showSlide(this.state.slides[0].id);
                this.scheduleNextSlide();
            } else {
                // Fallback: mostrar solo panel de datos
                this.showSlide('slide_data_panel');
            }
        } catch (error) {
            this.handleError("Error procesando configuración", error);
            // Fallback: mostrar solo panel de datos
            this.showSlide('slide_data_panel');
        }
    }

    createVideoSlide(slide) {
        const slideId = `slide_video_${slide.id}`;
       
        // Verificar si ya existe para evitar duplicados
        if (document.getElementById(slideId)) {
            return;
        }
       
        const videoHTML = `
            <div id="${slideId}" class="slide" style="display: none;">
                <video muted playsinline preload="metadata" style="width: 100%; height: 100%; object-fit: cover;">
                    <source src="/static/videos/${slide.filename}" type="video/mp4">
                    Tu navegador no soporta el tag de video.
                </video>
            </div>`;
       
        const slidesContainer = document.getElementById('slides-container');
        if (slidesContainer) {
            slidesContainer.insertAdjacentHTML('beforeend', videoHTML);
           
            // Configurar evento cuando el video termine
            const video = document.querySelector(`#${slideId} video`);
            if (video) {
                video.onended = () => {
                    console.log(`🎬 Video ${slide.filename} terminado, siguiente slide`);
                    this.nextSlide();
                };
               
                video.onerror = () => {
                    console.warn(`⚠️ Error cargando video ${slide.filename}`);
                    this.nextSlide();
                };
            }
        }
    }

    showSlide(slideId) {
        console.log(`📺 Mostrando slide: ${slideId}`);
       
        // Ocultar todos los slides
        document.querySelectorAll('.slide').forEach(s => s.style.display = 'none');
       
        // Mostrar el slide solicitado
        const slideEl = document.getElementById(slideId);
        if (!slideEl) {
            console.warn(`⚠️ Slide ${slideId} no encontrado`);
            return;
        }
       
        slideEl.style.display = 'block';
       
        // Si es un video, reproducirlo
        const video = slideEl.querySelector('video');
        if (video) {
            video.currentTime = 0;
            video.play().catch(e => {
                console.warn(`⚠️ El video no pudo iniciarse automáticamente:`, e.name);
                // Si no se puede reproducir automáticamente, pasar al siguiente
                setTimeout(() => this.nextSlide(), 1000);
            });
        }
    }

    scheduleNextSlide() {
        // Limpiar timeout anterior
        if (this.state.currentTimeout) {
            clearTimeout(this.state.currentTimeout);
            this.state.currentTimeout = null;
        }
       
        // Si solo hay un slide, no programar rotación
        if (this.state.slides.length <= 1) {
            console.log('📋 Solo hay un slide, no se programa rotación');
            return;
        }
       
        const currentSlide = this.state.slides[this.state.currentSlideIdx];
       
        // Solo programar timeout para slides de datos (los videos usan onended)
        if (currentSlide && currentSlide.type === 'data') {
            const delay = (currentSlide.duration || 30) * 1000;
            console.log(`⏰ Programando siguiente slide en ${delay/1000}s`);
            this.state.currentTimeout = setTimeout(() => this.nextSlide(), delay);
        }
    }

    nextSlide() {
        if (this.state.slides.length <= 1) return;
       
        // Limpiar timeout si existe
        if (this.state.currentTimeout) {
            clearTimeout(this.state.currentTimeout);
            this.state.currentTimeout = null;
        }
       
        // Avanzar al siguiente slide
        this.state.currentSlideIdx = (this.state.currentSlideIdx + 1) % this.state.slides.length;
        const nextSlide = this.state.slides[this.state.currentSlideIdx];
       
        console.log(`➡️ Cambiando a slide ${this.state.currentSlideIdx + 1}/${this.state.slides.length}: ${nextSlide.id}`);
       
        this.showSlide(nextSlide.id);
        this.scheduleNextSlide();
    }

    async updateData() {
        if (!this.state.isOnline) return;
        try {
            const response = await fetch('/data');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            this.updateUI(data);
        } catch (error) {
            this.handleError('Error actualizando datos', error);
        }
    }

    startDataUpdateLoop() {
        setInterval(() => this.updateData(), this.config.dataUpdateInterval);
    }

    updateUI(data) {
        const { air={}, co2={}, thr={}, pool={}, people={}, solar={} } = data;
        this.updateAirChart(air);
        this.updateSolarChart(solar);
        this.updatePeopleData(people);
        this.updateCO2Data(co2);
        this.updateTemperatureHumidity(thr);
        this.updatePoolData(pool);
    }
   
    updateElement(id, value, suffix = '') {
        const el = this.elements[id];
        if (el) el.textContent = value != null ? `${value}${suffix}` : '–';
    }

    updateAirChart(data) {
        const vals = ['no2','o3','so2','co','pm1','pm25','pm10'].map(k => data[k] || 0);
        if (!this.state.charts.air) {
            const ctx = this.elements.chartAir?.getContext('2d');
            if (!ctx) return;
            this.state.charts.air = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels:['NO₂','O₃','SO₂','CO','PM1','PM2.5','PM10'],
                    datasets:[{
                        data: vals,
                        backgroundColor:'rgba(103,126,234,0.7)',
                        borderRadius:6
                    }]
                },
                options: {
                    responsive:true,
                    maintainAspectRatio:false,
                    scales:{ y:{ beginAtZero:true } }
                }
            });
        } else {
            this.state.charts.air.data.datasets[0].data = vals;
            this.state.charts.air.update('none');
        }
    }

    updateSolarChart(data) {
        const vals = [data.generated_kwh||0, data.consumed_kwh||0];
        this.updateElement('solarRatioValue', data.import_export_ratio?.toFixed(2));
        if (!this.state.charts.solar) {
            const ctx = this.elements.chartSolar?.getContext('2d');
            if (!ctx) return;
            this.state.charts.solar = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels:['Generada','Consumida'],
                    datasets:[{
                        data: vals,
                        backgroundColor:['rgba(72,187,120,0.7)','rgba(245,101,101,0.7)'],
                        borderRadius:6
                    }]
                },
                options: {
                    responsive:true,
                    maintainAspectRatio:false,
                    scales:{ y:{ beginAtZero:true } }
                }
            });
        } else {
            this.state.charts.solar.data.datasets[0].data = vals;
            this.state.charts.solar.update('none');
        }
    }

    updatePeopleData(data) {
        this.updateElement('peopleTotalValue', data.total_complejo);
        this.updateElement('peopleGymValue', data.sala_gimnasio);
        this.updateProgressBar('peopleTotalProgress', data.total_complejo, this.config.capacities.total_complejo);
        this.updateProgressBar('peopleGymProgress', data.sala_gimnasio, this.config.capacities.sala_gimnasio);
    }

    updateProgressBar(id, value, max) {
        const el = this.elements[id];
        if (!el || value == null) return;
        const pct = Math.min((value / max) * 100, 100);
        el.style.width = `${pct}%`;
        el.className = `progress-bar ${ pct<70? 'bg-success': pct<90?'bg-warning':'bg-danger' }`;
    }

    updateCO2Data(data) {
        this.updateElement('co2Value', data.co2);
        const el = this.elements.co2Status;
        if (!el || data.co2 == null) return;
        let cls='good', txt='Excelente', ic='fa-check-circle';
        if (data.co2 > this.config.thresholds.co2.warning) {
            cls='warning'; txt='Elevado'; ic='fa-exclamation-triangle';
        }
        if (data.co2 > this.config.thresholds.co2.good * 1.5) {
            cls='danger'; txt='Alto'; ic='fa-times-circle';
        }
        el.className = `status-indicator ${cls}`;
        el.innerHTML = `<i class="fas ${ic}"></i><span>${txt}</span>`;
    }

    updateTemperatureHumidity(data) {
        this.updateElement('tempValue', data.temperature?.toFixed(1), '°C');
        this.updateElement('humValue', data.humidity ? (data.humidity*100).toFixed(0): null, '%');
    }
   
    updatePoolData(data) {
        this.updateElement('poolPhValue', data.ph?.toFixed(2));
        this.updateElement('poolTempValue', data.temperatura_agua?.toFixed(1), '°C');
        this.updateElement('poolCloroLibreValue', data.cloro_libre?.toFixed(2));
        this.updateElement('poolCloroTotalValue', data.cloro_total?.toFixed(2));
        this.updateElement('poolTurbidezValue', data.turbidez_ntu?.toFixed(2));
       
        // Calcular cloro residual (diferencia entre total y libre)
        if (data.cloro_total && data.cloro_libre) {
            const residual = data.cloro_total - data.cloro_libre;
            this.updateElement('poolCloroResidualValue', residual.toFixed(2));
        }
    }

    handleError(msg, err) {
        console.error(`❌ ${msg}:`, err);
    }

    showNotification(msg, type='info') {
        const el = document.createElement('div');
        el.className = `alert alert-${type} position-fixed`;
        el.style.cssText = 'top:20px; right:20px; z-index:9999; max-width:300px;';
        el.textContent = msg;
        document.body.appendChild(el);
        setTimeout(() => el.remove(), 4000);
    }
}

// Iniciar cuando la página esté completamente cargada
window.addEventListener('load', () => {
    window.dashboardApp = new DashboardApp();
});
