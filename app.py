import os
import pandas as pd
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import io
from werkzeug.utils import secure_filename
from flask import jsonify
import csv

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

# esta seccion es para la interaccion con la DDBB


@app.route('/manage_nits')
def manage_nits():
    """Render the NIT management interface"""
    conn = get_db_connection()
    nits = conn.execute('SELECT * FROM emisores ORDER BY nit').fetchall()
    categorias = conn.execute('SELECT DISTINCT categoria FROM emisores').fetchall()
    conn.close()
    return render_template('manage_nits.html', nits=nits, categorias=[row['categoria'] for row in categorias])

@app.route('/nit', methods=['POST'])
def add_nit():
    """Add a single NIT"""
    nit = request.form.get('nit')
    categoria = request.form.get('categoria')
    empresa = request.form.get('empresa')
    
    if not nit or not categoria or not empresa:
        return jsonify({'error': 'NIT, empresa y categoría son requeridos'}), 400
    
    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO emisores (nit, empresa, categoria) VALUES (?, ?, ?)',
                    (nit, empresa, categoria))  
        conn.commit()
        return jsonify({'message': 'NIT agregado exitosamente'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'El NIT ya existe'}), 400
    finally:
        conn.close()

@app.route('/nit/<nit>', methods=['PUT'])
def update_nit(nit):
    """Update a NIT's company name and category"""
    data = request.get_json()
    empresa = data.get('empresa')
    categoria = data.get('categoria')
    
    if not empresa or not categoria:
        return jsonify({'error': 'Empresa y categoría son requeridas'}), 400
    
    conn = get_db_connection()
    try:
        result = conn.execute('UPDATE emisores SET empresa = ?, categoria = ? WHERE nit = ?',
                            (empresa, categoria, nit))
        conn.commit()
        if result.rowcount == 0:
            return jsonify({'error': 'NIT no encontrado'}), 404
        return jsonify({'message': 'Empresa y categoría actualizadas exitosamente'})
    finally:
        conn.close()

@app.route('/nit/<nit>', methods=['DELETE'])
def delete_nit(nit):
    """Delete a NIT"""
    conn = get_db_connection()
    try:
        result = conn.execute('DELETE FROM emisores WHERE nit = ?', (nit,))
        conn.commit()
        if result.rowcount == 0:
            return jsonify({'error': 'NIT no encontrado'}), 404
        return jsonify({'message': 'NIT eliminado exitosamente'})
    finally:
        conn.close()

@app.route('/bulk_upload', methods=['POST'])
def bulk_upload():
    """Handle bulk upload of NITs via CSV"""
    if 'file' not in request.files:
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400
    
    file = request.files['file']
    if file.filename == '' or not file.filename.endswith('.csv'):
        return jsonify({'error': 'Archivo inválido. Debe ser un CSV'}), 400
    
    conn = get_db_connection()
    results = {
        'success': 0,
        'errors': []
    }
    
    try:
        # Create a StringIO object from the file content
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)
        
        # Verify required columns
        required_columns = {'nit', 'empresa', 'categoria'}
        if not required_columns.issubset(csv_reader.fieldnames):
            return jsonify({'error': 'El CSV debe contener las columnas: nit, empresa, categoria'}), 400
        
        for row in csv_reader:
            try:
                nit = row['nit'].strip()
                empresa = row['empresa'].strip()
                categoria = row['categoria'].strip()
                
                if not nit or not categoria:
                    results['errors'].append(f'Fila {csv_reader.line_num}: NIT, empresa y categoría son requeridos')
                    continue
                
                conn.execute('INSERT INTO emisores (nit, empresa, categoria) VALUES (?, ?, ?)',
                           (nit, categoria))
                results['success'] += 1
                
            except sqlite3.IntegrityError:
                results['errors'].append(f'Fila {csv_reader.line_num}: El NIT {nit} ya existe')
            except Exception as e:
                results['errors'].append(f'Fila {csv_reader.line_num}: Error - {str(e)}')
        
        conn.commit()
        return jsonify(results)
    
    except Exception as e:
        return jsonify({'error': f'Error al procesar el archivo: {str(e)}'}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=False)