# jenkins_integrator
This project is to setup a flask server which can forward the Github webhooks call to our Pipeline server, and format the parameters as Jenkins needed.

# How to build
```
docker image build . -t jk_flask
```

# How to run
```
docker run -it -p 7777:5000 jk_flask
```

