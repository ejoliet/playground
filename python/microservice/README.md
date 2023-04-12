# Directions

app.py together with dockerfile is a standalone microservice to resolve name using NED or Simbad created with the help of ChatGPT

in order to know the 'host' value, from docker run

`docker inspect --format '{{ .NetworkSettings.IPAddress }}' <container_id>`

And put this in app.run(host='IP-container',..)

`docker build -t my-image .`

`docker run -p 8099:5000 my-image`
