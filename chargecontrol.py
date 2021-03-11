import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')

from flask import Flask, jsonify, request, make_response, abort, send_from_directory, redirect, url_for
import relay


app = Flask(__name__)

def jsonify_no_content():
    response = make_response('', 204)
    response.mimetype = app.config['JSONIFY_MIMETYPE']
    return response


@app.route('/')
def index():
    return send_from_directory('ui/dist/ui', 'index.html')

@app.route('/<path:path>')
def send_static_content(path):
    return send_from_directory('ui/dist/ui', path)


@app.route('/api/chargecontrol')
def get_charge_control():
    ch = relay.readChannel1()
    return jsonify({
        'phases': 1 if ch else 3
    })


# curl -X PUT http://localhost:8080/api/chargecontrol/phases -H 'Content-Type: application/json' --data '1'
@app.route('/api/chargecontrol/phases', methods=['PUT'])
def put_charge_control():
    v = request.json
    if v == 1 or v == 3:
        # relay ON = 1 phase
        relay.writeChannel1(v == 1)
        return jsonify_no_content()
    else:
        abort(400)


if __name__ == '__main__':
    logging.info('Starting chargecontrol')
    app.run(host='0.0.0.0', port=8080)
    relay.cleanup()
    logging.info('Stopped chargecontrol')
