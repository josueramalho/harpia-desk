import imghdr
import os

def validate_image_header(stream):
    """
    Lê os primeiros bytes (magic numbers) do arquivo para garantir 
    que é realmente uma imagem e não um script malicioso renomeado.
    """
    header = stream.read(512)
    stream.seek(0)  # Reseta o ponteiro do arquivo para o início
    
    format = imghdr.what(None, header)
    if not format:
        return None
    return format

def is_safe_file(file):
    """
    Verifica se o arquivo tem uma extensão permitida e um header válido.
    """
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    
    filename = file.filename
    if '.' not in filename:
        return False
        
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False
        
    # Validação profunda (Magic Numbers)
    file_format = validate_image_header(file.stream)
    
    # Mapeamento de formatos do imghdr para extensões comuns
    valid_formats = ['jpeg', 'png', 'gif']
    
    return file_format in valid_formats