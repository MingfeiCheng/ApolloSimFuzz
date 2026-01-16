

FROM continuumio/miniconda3

WORKDIR /app

COPY . /app

RUN conda init bash

# Set timezone
ENV TZ=Asia/Singapore
RUN apt-get update -y && \
    apt-get install -y tzdata && \
    ln -fs /usr/share/zoneinfo/$TZ /etc/localtime && \
    dpkg-reconfigure --frontend noninteractive tzdata
    
RUN bash install.sh
