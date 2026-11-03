"""Local Steve/Alex skin mapping and printable-model workbench."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import math
import threading
from urllib.parse import urlsplit
from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image, UnidentifiedImageError
from voxfigure import body
from voxfigure.export_3mf import list_printer_templates

app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=2 * 1024 * 1024, MAX_FORM_PARTS=8)
_generation_lock = threading.Lock()

@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; frame-ancestors 'none'"
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/')
def index():
    return render_template('index.html')

@app.get('/api/options')
def options():
    return jsonify(models=['steve', 'alex'], printers=list_printer_templates())

def parameters():
    if set(request.form) - {'model', 'pixel_size', 'max_colors', 'printer'} or set(request.files) != {'skin'}:
        raise ValueError('请选择皮肤，仅支持普通 Steve / Alex 参数。')
    if any(len(request.form.getlist(key)) != 1 for key in request.form) or len(request.files.getlist('skin')) != 1:
        raise ValueError('参数不能重复。')
    model = request.form.get('model', 'steve')
    if model not in ('steve', 'alex'):
        raise ValueError('仅支持普通 Steve 和 Alex。')
    try:
        pixel = float(request.form.get('pixel_size', 2.5))
        colors = int(request.form.get('max_colors', 8))
    except ValueError:
        raise ValueError('请填写有效的尺寸和颜色数量。') from None
    if not math.isfinite(pixel) or not 1 <= pixel <= 5 or not 2 <= colors <= 32:
        raise ValueError('每像素尺寸应为 1–5 mm，颜色数量应为 2–32。')
    printers = {p['id'] for p in list_printer_templates()}
    printer = request.form.get('printer') or sorted(printers)[0]
    if printer not in printers:
        raise ValueError('请选择列表中的打印机。')
    return model, pixel, colors, printer

def process(exporting):
    origin = request.headers.get('Origin')
    if origin and urlsplit(origin).netloc != request.host:
        return jsonify(error='不接受跨站请求。'), 403
    try:
        model, pixel, colors, printer = parameters()
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if not _generation_lock.acquire(blocking=False):
        return jsonify(error='已有模型正在处理，请稍后重试。'), 409
    try:
        with TemporaryDirectory(prefix='voxfigure-') as directory:
            path = Path(directory) / 'skin.png'
            try:
                with Image.open(request.files['skin'].stream) as image:
                    if image.format != 'PNG' or image.size not in ((64, 64), (64, 32), (128, 128), (128, 64)):
                        raise ValueError('请上传 64 或 128 像素宽的标准 PNG 皮肤。')
                    image.convert('RGBA').save(path)
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
                return jsonify(error=str(e) if isinstance(e, ValueError) else '无法读取这张 PNG 皮肤。'), 400
            mesh = body.generate(path, model, pixel, colors)
            if not exporting:
                return jsonify(body.preview(mesh))
            target = Path(directory) / 'figure.3mf'
            body.export(mesh, target, printer)
            return send_file(BytesIO(target.read_bytes()), mimetype='model/3mf', as_attachment=True,
                             download_name=f'voxfigure-{model}.3mf')
    except ModuleNotFoundError:
        app.logger.exception('Missing runtime dependency')
        return jsonify(error='运行依赖不完整，请按 README 安装 requirements.txt 后重试。'), 503
    except Exception:
        app.logger.exception('Body processing failed')
        return jsonify(error='模型处理失败，请查看本地服务日志。'), 500
    finally:
        _generation_lock.release()

@app.post('/api/generate')
def generate():
    return process(False)

@app.post('/api/export')
def export():
    return process(True)

@app.errorhandler(413)
def too_large(error):
    return jsonify(error='皮肤文件不能超过 2 MB。'), 413

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False, threaded=True)
