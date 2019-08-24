FROM mysql:5.7

LABEL maintainer="Stephen Durham <sdurham@bluemoonforms.com>"

ENV MYSQL_DATABASE=units \
    MYSQL_ROOT_PASSWORD=hCc2CNACp4fh2VEF \
    MYSQL_USER=app \
    MYSQL_PASSWORD=EAVttkPzwSjxms4K \
    TZ=America/Chicago

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

EXPOSE 3306
