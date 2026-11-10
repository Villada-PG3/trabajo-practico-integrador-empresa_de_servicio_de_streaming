# Servicio de Streaming - RedFlix

**Grupo N.º: 10** 

## Integrantes

- Sarsur Al Farid
- Ferrazzuolo Benjamin
- Corti Ezequiel
- Fasioli Benjamin

## Descripción

Plataforma de streaming de video desarrollada en Django que permite la gestión de usuarios, perfiles (con restricción por edades), suscripciones a distintos planes, procesamiento simulado de cobros con validación de tarjetas por algoritmo de Luhn, catálogo dinámico de títulos/episodios y reproductor de video con subtítulos e historial de visualización.

---

## Instalación y set up

### 1. Clonar el repositorio

```bash
git clone git@github.com:Villada-PG3/trabajo-practico-integrador-empresa_de_servicio_de_streaming.git
cd trabajo-practico-integrador-empresa_de_servicio_de_streaming
```

### 2. Crear y activar un entorno virtual

**Linux / macOS**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell)**

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

### 3. Instalar las dependencias

```bash
pip install -r requirements.txt
```

---

## 🗄️ Inicialización y Reseteo de la Base de Datos

El modelo `Usuario` usa por defecto el país y el idioma con `id=1` (Argentina, Español), por lo que **deben existir antes de crear cualquier usuario**, incluido el superusuario.

Para generar una base de datos limpia desde cero, completamente poblada y sin registros incompletos:

```bash
# 1. Eliminar la base de datos previa (si existe)
rm -f db.sqlite3

# 2. Aplicar las migraciones del proyecto
python manage.py migrate

# 3. Cargar los datos iniciales y de prueba completos (mock.py)
python manage.py shell -c "exec(open('mock.py', encoding='utf-8').read())"

# 4. Crear el usuario Administrador (Superusuario)
python manage.py createsuperuser
```

> **Usuarios de prueba precreados por `mock.py`:**  
> `juan`, `maria`, `john`, `carla` (Contraseña para todos: `test1234`).

---

## 💳 Procesamiento Simulado de Cobros y Renovaciones

El sistema incluye un comando personalizado de Django que simula el procesamiento de cobros pendientes y la renovación periódica de las suscripciones.

### Ejecutar el script de cobros:

```bash
python manage.py procesar_cobros_demo
```

**Funcionamiento del comando:**
- Procesa y aprueba automáticamente los cobros en estado *"Por aprobar"* con más de 5 segundos de creación.
- Procesa las renovaciones periódicas de suscripciones activas según su fecha de vigencia.
- Aplica o cancela los cambios de plan programados por los usuarios.

---

## 📁 Archivos multimedia de demostración

Los archivos multimedia para la demostración del funcionamiento se encuentran organizados por tipo en la carpeta `media` en la raíz del proyecto, separados por idioma y calidad donde corresponde:
- **Formato de video:** MP4 (H.264 + AAC)
- **Formato de subtítulos:** WebVTT (`.vtt`, codificación UTF-8)

---

## 🚀 Ejecutar el servidor

```bash
python manage.py runserver
```

La aplicación queda disponible en:
- **Plataforma Web:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Panel de Administración (Jazzmin UI):** [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

---

## 📌 Características Principales

* **Panel Administrativo Personalizado:** Interfaz con estilo oscuro configurada mediante `django-jazzmin`.
* **Control de Acceso al Admin:** Botón de acceso directo al panel administrativo visible únicamente en perfiles de usuarios administradores (`is_staff` / `is_superuser`).
* **Reproductor de Video:** Muestra la etiqueta informativa `Nombre del Título | Nombre del Episodio` debajo de los controles de reproducción.
* **Validación de Tarjetas con Luhn:** Formulario de pago ficticio con validación estricta de tarjetas por el algoritmo de Luhn.
* **Gestión Multiperfil y Planes:** Control de límites de dispositivos simultáneos y tipos de perfil según la suscripción.