import sys
from website import create_app
from flask_babel import Babel, _
from subprocess import call

app = create_app()

if __name__ == '__main__':
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'extract':
            extract_messages()
        elif cmd == 'init' and len(sys.argv) > 2:
            init_locale(sys.argv[2])
        elif cmd == 'update':
            update_translations()
        elif cmd == 'compile':
            compile_translations()
        else:
            print("Usage: python main.py [extract|init <lang>|update|compile]")
    else:
        app.run(debug=True)
