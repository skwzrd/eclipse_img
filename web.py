import os

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for
)
from werkzeug.utils import secure_filename

from configs import CONSTS
from db import query_db
from db_api import get_sql_cols_from_d, get_sql_markers_from_d
from forms import SearchForm
from search import CLIPSearch, search_exif, search_ocr
from utils import get_current_datetime, get_current_datetime_w_us_str


def basename(path):
    return os.path.basename(path)


def create_app():
    app = Flask(__name__)
    app.secret_key = CONSTS.flask_secret
    app.config['UPLOAD_FOLDER'] = CONSTS.UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = CONSTS.MAX_CONTENT_LENGTH
    app.jinja_env.filters['basename'] = basename
    return app


app = create_app()
clip_search: CLIPSearch= CLIPSearch()


def save_text_or_file(text, file):
    if file:
        text = None

        unique_prefix = get_current_datetime_w_us_str()
        filename_secure = f'{unique_prefix}__{secure_filename(file.filename)}'
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename_secure)

        with open(filepath, 'wb') as f:
            file_data = file.read()
            f.write(file_data)
        os.chmod(filepath, 0o644) # o+r+w g+r a+r, no +x

    elif text:
        filepath = None

    else:
        raise ValueError()
    
    d = dict(
        query_text=text,
        query_filepath=filepath,
        current_datetime=get_current_datetime(),

        x_forwarded_for=request.headers.get("X-Forwarded-For", None),
        remote_addr=request.headers.get("Remote-Addr", None),
        referrer=request.referrer,
        content_md5=request.content_md5,
        origin=request.origin,
        scheme=request.scheme,
        method=request.method,
        root_path=request.root_path,
        path=request.path,
        query_string=request.query_string.decode(),
        user_agent=request.user_agent.__str__(),
        x_forwarded_proto=request.headers.get("X-Forwarded-Proto", None),
        x_forwarded_host=request.headers.get("X-Forwarded-Host", None),
        x_forwarded_prefix=request.headers.get("X-Forwarded-Prefix", None),
        host=request.headers.get("Host", None),
        connection=request.headers.get("Connection", None),
        content_length=request.content_length,
    )

    sql_string = f"""INSERT INTO search_log ({get_sql_cols_from_d(d)}) VALUES ({get_sql_markers_from_d(d)});"""
    query_db(sql_string, args=list(d.values()), commit=True)
    return text, filepath


@app.route('/', methods=['GET', 'POST'])
def index():
    form: SearchForm = SearchForm()
    results = []

    if form.validate_on_submit():
        text_clip = form.clip.data
        text_exif = form.exif.data
        text_ocr = form.ocr.data
        file = form.file.data

        if file:
            text_clip, filepath = save_text_or_file(text_clip, file)
            results = clip_search.search_with_image(filepath)
            flash(f"Showing results for the image.", 'success')

        else:
            if text_clip:
                results = clip_search.search_with_text(text_clip)
            elif text_exif:
                results = search_exif(text_exif)
            elif text_ocr:
                results = search_ocr(text_ocr)
            else:
                flash("No valid search criteria provided.", 'warning')

            if not results:
                flash('No results found', 'warning')

        form.data.clear()

    return render_template('index.html', form=form, results=results, search_result_limit=CONSTS.search_result_limit)


@app.route('/serve/<path:filename>')
def serve(filename: str):
    file_path = os.path.abspath(os.path.join('/', filename))
    if file_path.startswith(CONSTS.root_image_folder) and os.path.isfile(file_path):
        return send_file(file_path)
    abort(404)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9090, debug=True)

