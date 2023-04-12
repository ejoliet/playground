from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello, World!'

@app.route('/hello', methods=['GET'])
def helloworld():
    if(request.method == 'GET'):
        data = {"data": "Hello World"}
        return jsonify(data)

if __name__ == '__main__':
# After getting the ip address from docker inspect such as
# docker inspect --format '{{ .NetworkSettings.IPAddress }}' <container_id>
#replace here in 'host', then go to,localhost in the browser
    app.run(debug=True,host='172.17.0.2', port=8099)
    # Start the Gunicorn server with 4 worker processes
    # Listening on port 8080
   # app.run(host='0.0.0.0', port=8099, workers=4)
