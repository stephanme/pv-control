import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')

from flask import Flask, jsonify, request, make_response, abort
import relay


app = Flask(__name__)

def jsonify_no_content():
    response = make_response('', 204)
    response.mimetype = app.config['JSONIFY_MIMETYPE']
    return response

@app.route('/')
def hello():
    return 'Charge Control'

@app.route('/api/chargecontrol')
def get_charge_control():
    ch = relay.readChannel1()
    return jsonify({
        'phases': 1 if ch == 1 else 3
    })


# curl -X PUT http://localhost:8080/api/chargecontrol/phases -H 'Content-Type: application/json' --data '1'
@app.route('/api/chargecontrol/phases', methods=['PUT'])
def put_charge_control():
    v = request.json
    if v == 1 or v == 3:
        if (v == 3):
            relay.writeChannel1(0)
        else:
            relay.writeChannel1(1)
        return jsonify_no_content()
    else:
        abort(400)


if __name__ == '__main__':
    logging.info('Starting chargecontrol')
    app.run(host='0.0.0.0', port=8080)
    logging.info('Stopped chargecontrol')
