import jwt
import os
import logging
import enum
from random import randrange
import requests
import json
from sqlalchemy.exc import SQLAlchemyError
from flask import Flask, jsonify, abort, request
from flask_sqlalchemy import SQLAlchemy
from flask_swagger import swagger
from flask_swagger_ui import get_swaggerui_blueprint
from functools import wraps
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from flask_cors import CORS
from http import HTTPStatus

# Loading Config Parameters
DB_USER = os.getenv('DB_USER', 'wys')
DB_PASS = os.getenv('DB_PASSWORD', 'rac3e/07')
DB_IP = os.getenv('DB_IP_ADDRESS', '10.2.19.195')
DB_PORT = os.getenv('DB_PORT', '3307')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'wys')
APP_HOST = os.getenv('APP_HOST', '127.0.0.1')
APP_PORT = os.getenv('APP_PORT', 5007)
PROJECTS_MODULE_HOST = os.getenv('PROJECTS_MODULE_HOST', '127.0.0.1')
PROJECTS_MODULE_PORT = os.getenv('PROJECTS_MODULE_PORT', 5000)
PROJECTS_MODULE_API = os.getenv('PROJECTS_MODULE_API', '/api/projects/')
PROJECTS_URL = f"http://{PROJECTS_MODULE_HOST}:{PROJECTS_MODULE_PORT}"

# Flask Configurations
app = Flask(__name__)
CORS(app)
app.logger.setLevel(logging.DEBUG)

# SQL Alchemy Configurations
app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql://{DB_USER}:{DB_PASS}@{DB_IP}:{DB_PORT}/{DB_SCHEMA}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
Base = declarative_base()

# Swagger Configurations
SWAGGER_URL = '/api/times/docs/'
API_URL = '/api/times/spec'
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={  # Swagger UI config overrides
        'app_name': "WYS API - Times Service"
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Reading public key
try:
    f = open('oauth-public.key', 'r')
    key: str = f.read()
    f.close()
    app.config['SECRET_KEY'] = key
except Exception as terr:
    app.logger.error(f'Can\'t read public key f{terr}')
    exit(-1)


class RequirementsEnum(enum.Enum):
    """
    low: Low Value to consider in PriceValue
    medium: Medium Value to consider in PriceValue
    high: High value to consider in PriceValue
    """

    low = "LOW"
    medium = "MEDIUM"
    high = "HIGH"


class PriceModule(db.Model):
    """
    id: Id primary key
    name: Space name (Same name that are in spaces uservice)
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    values = db.relationship("PriceValue",
                             backref="price_module",
                             cascade="all, delete, delete-orphan")


class PriceCategory(db.Model):
    """
    id: Id primary key
    code: Category Name Code( Can be CALIDAD_TERMNACIONES, MOBILIARIO,
                                     CALIDAD_ACUSTICA, CONFORT_CLIMATICO,
                                     VELOCIDAD_RED, CONTROL_ILUMINACION,
                                     SEGURIDAD, TECNOLOGIA, ELECTRODOMESTICOS)
    name: Category Name that will be displayed in frontend (In spanish)
    """
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String, nullable=False)
    name = db.Column(db.String, nullable=True)
    values = db.relationship("PriceValue",
                             backref="price_category",
                             cascade="all, delete, delete-orphan")


class PriceGen(db.Model):
    """
    id:  Id primary key
    project_id: Project ID that you want to save this configurations
    value: Enum that indicate if the value to consider is LOW, MEDIUM or HIGH
    """

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False)
    value = db.Column(db.Enum(RequirementsEnum), nullable=False)


class PriceValue(db.Model):
    """
    id: Id primary key
    low: Value in USD related to a category and module
    medium: Value in USD related to a category and module
    high: Value in USD related to a category and module
    """
    id = db.Column(db.Integer, primary_key=True)
    low = db.Column(db.Float, nullable=False)
    medium = db.Column(db.Float, nullable=False)
    high = db.Column(db.Float, nullable=False)
    module_id = db.Column(db.Integer, db.ForeignKey('price_module.id'), nullable=False)
    country_id = db.Column(db.Integer, db.ForeignKey('price_country.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('price_category.id'), nullable=False)


class PriceCountry(db.Model):
    """
    id: Id primary key
    name: Country Name (Always in Upper Case and without specials chars)
    default: If this country is the default.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, nullable=False)
    default = db.Column(db.Boolean, nullable=False)
    values = db.relationship("PriceValue",
                             backref="price_country",
                             cascade="all, delete, delete-orphan")


if __name__ == '__main__':
    app.run(host=APP_HOST, port=APP_PORT, debug=True)
