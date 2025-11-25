# imghdr.py - простая замена для удаленного модуля

def what(file, h=None):
    """Определяет тип изображения по содержимому файла"""
    try:
        if h is None:
            if isinstance(file, str):
                with open(file, 'rb') as f:
                    h = f.read(32)
            else:
                location = file.tell()
                h = file.read(32)
                file.seek(location)
        
        if h.startswith(b'\xff\xd8'):
            return 'jpeg'
        if h.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'png'
        if h.startswith(b'GIF87a') or h.startswith(b'GIF89a'):
            return 'gif'
        if h.startswith(b'BM'):
            return 'bmp'
    except Exception:
        pass
    return None

tests = {}
