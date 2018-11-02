FROM kernsuite/base:3
MAINTAINER Ben Hugo "bhugo@ska.ac.za"

RUN mkdir /src
RUN mkdir /src/cubical
ADD cubical /src/cubical/cubical
ADD docs /src/cubical/docs
ADD examples /src/cubical/examples
ADD test /src/cubical/test
ADD .gitattributes /src/cubical/.gitattributes
ADD .gitignore /src/cubical/.gitignore
ADD .git /src/cubical/.git
ADD HEADER /src/cubical/HEADER
ADD LICENSE.md /src/cubical/LICENSE.md
ADD MANIFEST.in /src/cubical/MANIFEST.in
ADD README.md /src/cubical/README.md
ADD requirements.txt /src/cubical/requirements.txt
ADD requirements.test.txt /src/cubical/requirements.test.txt
ADD rtd_requirements.txt /src/cubical/rtd_requirements.txt
ADD setup.py /src/cubical/setup.py

WORKDIR /src/cubical
ENV DEB_DEPENDENCIES casacore-dev \
                     casacore-data \
                     build-essential \
                     python-pip \ 
                     libboost-all-dev \ 
                     wcslib-dev \
                     libcfitsio3-dev
RUN apt-get update
RUN apt-get install -y $DEB_DEPENDENCIES
RUN pip install -U pip wheel setuptools
RUN pip install -r requirements.txt
RUN python setup.py gocythonize
RUN pip install -U .

ENTRYPOINT ["gocubical"]
CMD ["--help"]
