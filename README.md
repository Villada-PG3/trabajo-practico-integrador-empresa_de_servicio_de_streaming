# Servicio de Streaming

**Grupo N.º: 10** 

## Integrantes

- Sarsur Al Farid
- Ferrazzuolo Benjamin
- Corti Ezequiel
- Fasioli Benjamin

## Descripción

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

### 4. Crear la base de datos

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Cargar los datos iniciales

El modelo `Usuario` usa por defecto el país y el idioma con `id=1` (argentina, español), por lo que **deben existir antes de crear cualquier usuario**, incluido el superusuario.

Para cargar los datos de prueba o 'mock' se debe primero abrir el shell
```bash
python manage.py shell
```
Y desde el shell ejecutar el archivo 'mock.py'
```python
> exec(open('mock.py', encoding='utf-8').read())
```

### 6. Crear el superusuario

```bash
python manage.py createsuperuser
```

### 8. Archivos multimedia de demostración

Los archivos multimedia para la demostración del funcionamiento se encuentran organizados por tipo en la carpeta en el root del proyecto media separados por idioma y calidad donde corresponde
- Formato de video: MP4 (H.264 + AAC)
- Formato de subtítulos: WebVTT (`.vtt`, codificación UTF-8)

### 9. Ejecutar el servidor

```bash
python manage.py runserver
```
La aplicación queda disponible en <http://127.0.0.1:8000/> y el panel de administración en <http://127.0.0.1:8000/admin/>.