from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
import pytz

app = Flask(__name__)

@app.route('/')
def index():
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Adaptive Time based on User's Location</title>
</head>
<body>
    <h2>Adaptive Time based on User's Location</h2>
    <p>We will adjust the time to your local timezone.</p>
    <p><strong>Current Time in Your Local Timezone:</strong> <span id="local-time">Loading...</span></p>

    <script>
        const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

        function fetchTime() {
            const url = new URL('/adjust-time', window.location.origin);
            url.searchParams.set('timezone', userTimezone);

            fetch(url)
                .then(response => response.json())
                .then(data => {
                    if (data.local_time) {
                        document.getElementById('local-time').innerText = data.local_time;
                    } else {
                        document.getElementById('local-time').innerText = 'Error fetching time';
                    }
                })
                .catch(err => {
                    document.getElementById('local-time').innerText = 'Fetch error';
                    console.error(err);
                });
        }

        fetchTime();
    </script>
</body>
</html>
""")

@app.route('/adjust-time')
def adjust_time():
    user_timezone = request.args.get('timezone')
    if not user_timezone:
        return jsonify({'error': 'No timezone provided'}), 400

    try:
        tz = pytz.timezone(user_timezone)
    except pytz.UnknownTimeZoneError:
        return jsonify({'error': f'Unknown timezone: {user_timezone}'}), 400

    now = datetime.now(tz)
    formatted_time = now.strftime('%Y-%m-%d %H:%M:%S %Z%z')
    return jsonify({'local_time': formatted_time})

if __name__ == '__main__':
    app.run(debug=True)
