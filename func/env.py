import os

from dotenv import load_dotenv, find_dotenv

__all__ = ['LOAD_ENV', 'GET_ENV']

def LOAD_ENV():
    load_dotenv(find_dotenv())

def GET_ENV(key):
    return os.getenv(key)