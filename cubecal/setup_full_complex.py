from distutils.core import setup
from distutils.extension import Extension
from Cython.Distutils import build_ext
import numpy as np

setup(
	cmdclass = {'build_ext': build_ext},
    	ext_modules=[Extension("cyphase_only", ["cyphase_only.pyx"],
               	include_dirs=[np.get_include()],
		extra_compile_args=['-fopenmp','-ffast-math','-O2','-march=native',
							'-mtune=native', '-ftree-vectorize'],
		extra_link_args=['-lgomp'])]
	)
