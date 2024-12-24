import os
import pandas as pd
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import io
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config.update(
    UPLOAD_FOLDER='uploads',
    ALLOWED_EXTENSIONS={'xls', 'xlsx', 'csv'},
    MAX_CONTENT_LENGTH=16 * 1024 * 1024  # 16MB max-limit
    #SECRET_KEY='your-secret-key-here'  # Necesario para flash messages
)

# Crear carpetas necesarias
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('database', exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_db_connection():
    conn = sqlite3.connect('database/database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    # Limpiar archivos temporales anteriores
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f'Error: {e}')
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No se seleccionó ningún archivo')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No se seleccionó ningún archivo')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Leer el archivo
            if filename.endswith('.csv'):
                df = pd.read_csv(filepath)
            else:
                df = pd.read_excel(filepath)
            
            # Verificar si existe la columna 'NIT del emisor'
            if 'NIT del emisor' not in df.columns:
                flash('El archivo debe contener una columna llamada NIT del emisor', 'error')
                return redirect(url_for('index'))
            
            # Obtener NITs únicos
            nits = df['NIT del emisor'].unique()
            conn = get_db_connection()
            
            # Crear diccionario de NITs y categorías
            nits_con_categoria = {}
            unmatched_nits = []
            
            # Buscar categorías existentes
            for nit in nits:
                result = conn.execute('SELECT categoria FROM emisores WHERE nit = ?', (nit,)).fetchone()
                if result:
                    nits_con_categoria[nit] = result['categoria']
                else:
                    nits_con_categoria[nit] = None
                    unmatched_nits.append(nit)
            
            conn.close()
            
            # Si hay NITs sin categoría
            if unmatched_nits:
                return render_template('assign_category.html', 
                                    nits=unmatched_nits, 
                                    filename=filename)
            
            # Si todos los NITs tienen categoría, actualizar el archivo
            df['categoria'] = df['NIT del emisor'].map(nits_con_categoria)
            
            # Guardar el archivo actualizado
            output = io.BytesIO()
            if filename.endswith('.csv'):
                df.to_csv(output, index=False)
                mimetype = 'text/csv'
                download_name = 'archivo_actualizado.csv'
            else:
                df.to_excel(output, index=False)
                mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                download_name = 'archivo_actualizado.xlsx'
            
            output.seek(0)
            os.remove(filepath)  # Eliminar archivo temporal
            return send_file(
                output,
                as_attachment=True,
                download_name=download_name,
                mimetype=mimetype
            )
            
        except Exception as e:
            if os.path.exists(filepath):
                os.remove(filepath)
            flash(f'Error al procesar el archivo: {str(e)}')
            return redirect(url_for('index'))


@app.route('/assign_categories', methods=['POST'])
def assign_categories():
    filename = request.form.get('filename')
    if not filename:
        flash('Error: Nombre de archivo no proporcionado')
        return redirect(url_for('index'))
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        flash('Error: El archivo ya no existe')
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    try:
        # Guardar nuevas categorías
        for key, value in request.form.items():
            if key.startswith('categoria_'):
                nit = key.replace('categoria_', '')
                if value.strip():  # Solo si la categoría no está vacía
                    conn.execute('INSERT INTO emisores (nit, categoria) VALUES (?, ?)',
                               (nit, value))
        conn.commit()
        
        # Leer el archivo original
        if filename.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
        
        # Convertir la columna NIT a string
        df['NIT del emisor'] = df['NIT del emisor'].astype(str)
        
        # Obtener todas las categorías actualizadas
        nits = df['NIT del emisor'].unique()
        nits_con_categoria = {}
        
        # Usar una sola consulta para obtener todas las categorías
        placeholders = ','.join('?' * len(nits))
        query = f'SELECT nit, categoria FROM emisores WHERE nit IN ({placeholders})'
        results = conn.execute(query, [str(nit) for nit in nits]).fetchall()
        
        # Crear diccionario de NITs y categorías
        for row in results:
            nits_con_categoria[str(row['nit'])] = row['categoria']
        
        # Actualizar el DataFrame con las categorías
        df['categoria'] = df['NIT del emisor'].map(nits_con_categoria)
        
        # Preparar el archivo para descarga
        output = io.BytesIO()
        if filename.endswith('.csv'):
            df.to_csv(output, index=False)
            mimetype = 'text/csv'
            download_name = 'archivo_actualizado.csv'
        else:
            df.to_excel(output, index=False)
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            download_name = 'archivo_actualizado.xlsx'
        
        output.seek(0)
        
        # Limpiar recursos
        conn.close()
        if os.path.exists(filepath):
            os.remove(filepath)
        # Mostrar mensaje de éxito y descargar el archivo, y luego redirigir a la página principal
        
        flash('¡Archivo procesado exitosamente! La descarga comenzará en un momento.')

        response = send_file(
            output,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype
        )
        response.headers["Content-Disposition"] = f"attachment; filename={download_name}"

        return response     

    except Exception as e:
        conn.close()
        if os.path.exists(filepath):
            os.remove(filepath)
        flash(f'Error al procesar el archivo: {str(e)}')
        return redirect(url_for('index'))

# [Rest of the code remains the same]

if __name__ == '__main__':
    app.run(debug=False)