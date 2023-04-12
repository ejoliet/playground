from flask import Flask, request, jsonify
from astroquery.simbad import Simbad
from astroquery.ned import Ned

# create a microservice that can resolve a name with either Simbad or NED, we will need to first define the endpoints and methods for our service, and then implement the functionality to query the respective databases.



app = Flask(__name__)

# define endpoint to resolve name with Simbad
@app.route('/simbad/<string:name>', methods=['GET'])
def resolve_simbad(name):
    result = Simbad.query_object(name)
    if result is not None:
        ra = result['RA'][0]
        dec = result['DEC'][0]
        return jsonify({'name': name, 'ra': ra, 'dec': dec})
    else:
        return jsonify({'error': 'Object not found in Simbad database'})

# define endpoint to resolve name with NED
@app.route('/ned/<string:name>', methods=['GET'])
def resolve_ned(name):
    result = Ned.query_object(name)
    if result is not None:
        ra = result['RA'][0]
        dec = result['DEC'][0]
        return jsonify({'name': name, 'ra': ra, 'dec': dec})
    else:
        return jsonify({'error': 'Object not found in NED database'})

if __name__ == '__main__':
    app.run(host='172.17.0.2', debug=True)

