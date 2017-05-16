# CubiCal

## Requirements

* numpy >= 1.11.3
* cython >= 0.25.2
* futures >= 3.0.5
* python-casacore >= 2.1.2

## Instructions

* Create and activate a virtualenv as described below.
* Clone the repository.
* To install all requirements EXCLUDING montblanc:

```
   $ pip install -r CubiCal/requirements.txt
```

* Install with:

```
   $ pip install CubiCal/
```

* Developers should install with:

```
   $ pip install -e CubiCal/
```

This will install CubiCal in development mode.

* CubiCal can be run from command line using:

```
   $ gocubical
```	 

If this doesn't work, add path/to/your/virtual/env/bin/gocubical to your path.

* -h or --help will display the currently available options.

## Setting up a virtual environment

* To install virtualenv with pip:

```
$ pip install virtualenv
```

* To create and activate a virtual environment:

```
$ virtualenv cubienv   # or pick any other name
$ source cubienv/bin/activate
```




