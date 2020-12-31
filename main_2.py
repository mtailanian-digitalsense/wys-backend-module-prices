import enum
import logging
import random
import os
import pprint
from functools import wraps
from http import HTTPStatus

import jwt
import json
import pandas as pd
from flask import Flask, jsonify, abort, request
import requests
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_swagger import swagger
from flask_swagger_ui import get_swaggerui_blueprint
from sqlalchemy.ext.declarative import declarative_base

import constants

# Loading Config Parameters
DB_USER = os.getenv('DB_USER', 'wys')
DB_PASS = os.getenv('DB_PASSWORD', 'rac3e/07')
DB_IP = os.getenv('DB_IP_ADDRESS', '10.2.19.195')
DB_PORT = os.getenv('DB_PORT', '3307')
DB_SCHEMA = os.getenv('DB_SCHEMA', 'wys')
APP_HOST = os.getenv('APP_HOST', '127.0.0.1')
APP_PORT = os.getenv('APP_PORT', 5008)
PROJECTS_MODULE_HOST = os.getenv('PROJECTS_MODULE_HOST', '127.0.0.1')
PROJECTS_MODULE_PORT = os.getenv('PROJECTS_MODULE_PORT', 5000)
PROJECTS_MODULE_API = os.getenv('PROJECTS_MODULE_API', '/api/projects/')
PROJECTS_URL = f"http://{PROJECTS_MODULE_HOST}:{PROJECTS_MODULE_PORT}"

SPACES_MODULE_HOST = os.getenv('SPACES_MODULE_HOST', '127.0.0.1')
SPACES_MODULE_PORT = os.getenv('SPACES_MODULE_PORT', 5002)
SPACES_MODULE_API = os.getenv('SPACES_MODULE_API', '/api/spaces/')

TIMES_MODULE_HOST = os.getenv('TIMES_MODULE_HOST', '127.0.0.1')
TIMES_MODULE_PORT = os.getenv('TIMES_MODULE_PORT', 5007)
TIMES_MODULE_API = os.getenv('TIMES_MODULE_API', '/api/times')
TIMES_URL = f"http://{TIMES_MODULE_HOST}:{TIMES_MODULE_PORT}"

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
SWAGGER_URL = '/api/prices/docs/'
API_URL = '/api/prices/spec'
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
    name = db.Column(db.String(100), nullable=False)
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
    code = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(100), nullable=True)
    type = db.Column(db.CHAR, nullable=False, default='A')
    parent_category_id = db.Column(db.Integer, db.ForeignKey('price_category.id'))
    subcategories = db.relationship("PriceCategory",
                 backref=db.backref('price_category', remote_side=[id]),
                 cascade="all, delete, delete-orphan"
                ) 
    values = db.relationship("PriceValue",
                             backref="price_category",
                             cascade="all, delete, delete-orphan")

    def to_dict(self, full=False):
        obj_dict = {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'type': self.type
        }
        if full:
            obj_dict['parent_category_id'] = self.parent_category_id
            obj_dict['subcategories'] = [subcategory.to_dict() for subcategory in self.subcategories]
        return obj_dict

    def serialize(self, full=False):
        return jsonify(self.to_dict(full))


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
    low = db.Column(db.Float, nullable=False, default=0.0)
    medium = db.Column(db.Float, nullable=False, default=0.0)
    high = db.Column(db.Float, nullable=False, default=0.0)
    module_id = db.Column(
        db.Integer,
        db.ForeignKey('price_module.id'),
        nullable=True)
    country_id = db.Column(
        db.Integer,
        db.ForeignKey('price_country.id'),
        nullable=True)
    category_id = db.Column(
        db.Integer,
        db.ForeignKey('price_category.id'),
        nullable=True)

    def to_dict(self):
        obj_dict = {
            'id': self.id,
            'low': self.low,
            'medium': self.medium,
            'high': self.high,
            'module_id': self.module_id,
            'country_id': self.country_id,
            'category_id': self.category_id
        }
        return obj_dict

    def serialize(self):
        return jsonify(self.to_dict())

class PriceCountry(db.Model):
    """
    id: Id primary key
    name: Country Name (Always in Upper Case and without specials chars)
    default: If this country is the default.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    default = db.Column(db.Boolean, nullable=False, default=False)
    values = db.relationship("PriceValue",
                             backref="price_country",
                             cascade="all, delete, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'default': self.default,
        }


db.create_all()


def token_required(f):
    @wraps(f)
    def decorator(*args, **kwargs):

        bearer_token = request.headers.get('Authorization', None)
        try:
            token = bearer_token.split(" ")[1]
        except Exception as ierr:
            app.logger.error(ierr)
            return jsonify({'message': 'a valid bearer token is missing'}), 500

        if not token:
            app.logger.debug("token_required")
            return jsonify({'message': 'a valid token is missing'})

        app.logger.debug("Token: " + token)
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'],
                              algorithms=['RS256'], audience="1")
            user_id: int = data['user_id']
            request.environ['user_id'] = user_id
        except Exception as err:
            return jsonify({'message': 'token is invalid', 'error': err})
        except KeyError as kerr:
            return jsonify(
                {'message': 'Can\'t find user_id in token', 'error': kerr})

        return f(*args, **kwargs)

    return decorator


def get_project_weeks(m2, token):
    try:
        headers = {'Authorization': token}
        data = {
            "adm_agility": "normal",
            "client_agility": "normal",
            "construction_mod": "const_adm",
            "constructions_times": "daytime",
            "demolitions": "no",
            "m2": m2,
            "mun_agility": "normal",
            "procurement_process": "direct"
        }
        resp = requests.post(
            f'{TIMES_URL}{TIMES_MODULE_API}', headers=headers, json=data)
        resp_data = json.loads(resp.text)
        return resp_data['weeks']
    except Exception as exp:
        logging.error(f"Error getting spaces {exp}")
        return f"Error getting spaces {exp}", 500

@app.route("/api/prices/spec", methods=['GET'])
@token_required
def spec():
    swag = swagger(app)
    swag['info']['version'] = "1.0"
    swag['info']['title'] = "WYS Prices API Service"
    swag['tags'] = [{
        "name": "Prices",
        "description": "Methods to configure Prices"
    }]
    return jsonify(swag)


'''@app.route('/api/prices/upload', methods=['POST'])
def upload_prices():
    """
        Upload/Update Prices
        ---
        tags:
        - "Prices"
        produces:
        - "application/json"
        consumes:
        - "multipart/form-data"
        parameters:
        - name: "file"
          in: "formData"
          description: "File to upload"
          required: true
          type: file
    """

    # Verify that archive is a Excel spreadsheet (xls or xlsx)
    # Check if the post request has the file part
    if 'file' not in request.files:
        abort(HTTPStatus.BAD_REQUEST, "No Multipart file found")
    file = request.files['file']

    if file.filename == '':
        logging.warning('No selected File')
        return jsonify({'message': "No selected file"}), HTTPStatus.BAD_REQUEST

    filename: str = file.filename

    filename_split: [] = filename.split('.')

    if not (filename_split[-1] == constants.VALID_EXTENSIONS_XLS or
            filename_split[-1] == constants.VALID_EXTENSIONS_XLSX):
        logging.warning(f'{filename_split[-1]} is not a valid extension')
        return {
            'message': f'{filename_split[-1]} is not a valid extension'}, 420

    # Read sheets names as country name
    if filename_split[-1] == constants.VALID_EXTENSIONS_XLSX:
        sheets: dict = pd.read_excel(file, None, engine='openpyxl')
    else:
        sheets: dict = pd.read_excel(file, None)

    logging.debug(sheets)

    # For Each sheet
    for country_name in sheets:
        try:
            # If country exist take id, else, create a new country and take the
            # new id
            country: PriceCountry = PriceCountry.query \
                .filter(PriceCountry.name == country_name.upper()) \
                .first()

            country_id: int
            if country is None:
                country = PriceCountry()
                country.name = country_name.upper()
                country.code = country_name.upper()
                db.session.add(country)
                db.session.commit()

            country_id = country.id

        except Exception as exp:
            logging.error(f"Error in database {exp}")
            db.session.rollback()
            return jsonify({'message': f"Error in database {exp}"}), 500

        modules_hash = {}
        category_hash = {}

        for row in sheets[country_name].iterrows():
            # Read Column "MODULO" and find Module by name
            module_name = row[1][constants.ROW_MODULO]
            if module_name not in modules_hash:
                logging.debug(module_name)
                module: PriceModule = PriceModule.query.filter(
                    PriceModule.name == module_name).first()
                module_id: int
                if module is None:
                    try:
                        module = PriceModule()
                        module.name = module_name
                        db.session.add(module)
                        db.session.commit()
                        modules_hash[module_name] = module

                    except Exception as exp:
                        logging.error(f"Database error. {exp}")
                        db.session.rollback()
                        return jsonify({'message': f"Database error. {exp}"}), 500
                else:
                    modules_hash[module_name] = module

            # Read Column "PARAMETRO" and find a "PriceCategory"
            category_name = row[1][constants.ROW_PARAMETRO]
            if category_name not in category_hash:
                category: PriceCategory = PriceCategory.query \
                    .filter(PriceCategory.name == category_name) \
                    .first()

                # If PriceCategory exist get id else create and get the id.
                if category is None:
                    try:
                        category = PriceCategory()
                        category.name = category_name
                        category.code = category_name
                        db.session.add(category)
                        db.session.commit()
                        category_hash[category_name] = category

                    except Exception as exp:
                        logging.error(f'Database error. {exp}')
                        db.session.rollback()
                        return jsonify({'message': f"Database error. {exp}"}), 500
                else:
                    category_hash[category_name] = category

            # Read columns "ESTANDAR BAJO", "ESTANDAR MEDIO", "ESTANDAR ALTO".
            try:
                low: float = row[1][constants.ROW_BAJO]
                medium: float = row[1][constants.ROW_MEDIO]
                high: float = row[1][constants.ROW_ALTO]

            except Exception as exp:
                msg = f"Error reading rows: {constants.ROW_BAJO}, " \
                      f"{constants.ROW_MEDIO}, {constants.ROW_ALTO}: {exp}"
                logging.error(msg)
                return jsonify({"message": msg}), 421

            # Get a price value by PriceCountry, PriceCategory and PriceModule. If Exist
            # get Object else, create a new object. Update or create the values
            # low, medium and high.
            module_id = modules_hash[module_name].id
            category_id = category_hash[category_name].id

            module = modules_hash[module_name]
            category = category_hash[category_name]

            try:
                value = PriceValue.query.filter(
                    PriceValue.module_id == modules_hash[module_name].id) .filter(
                    PriceValue.country_id == country_id) .filter(
                    PriceValue.category_id == category_id) .first()
            except Exception as exp:
                logging.error(f"Database error {exp}")
                return jsonify({'message': f"Database error {exp}"}), 500

            if value is None:
                value = PriceValue()
                try:
                    country.values.append(value)
                    db.session.commit()
                    category.values.append(value)
                    db.session.commit()
                    module.values.append(value)
                    db.session.commit()
                except Exception as exp:
                    logging.error(f"Database error {exp}")
                    return jsonify({'message': f"Database error {exp}"}), 500

            value.low = low
            value.medium = medium
            value.high = high

            # commit database
            try:
                db.session.commit()
            except Exception as exp:
                db.session.rollback()
                logging.error(f"Database error {exp}")
                return jsonify({'message': f"Database error {exp}"}), 500

    # Return status
    return jsonify({'status': 'OK'})'''

@app.route('/api/prices/upload', methods=['POST'])
def upload_prices_v2():
    """
        Upload/Update Prices
        ---
        tags:
        - "Prices"
        produces:
        - "application/json"
        consumes:
        - "multipart/form-data"
        parameters:
        - name: "file"
          in: "formData"
          description: "File to upload"
          required: true
          type: file
    """

    ''' Verify that archive is a Excel spreadsheet (xls or xlsx)'''
    # Check if the post request has the file part
    if 'file' not in request.files:
        abort(HTTPStatus.BAD_REQUEST, "No Multipart file found")
    file = request.files['file']

    if file.filename == '':
        logging.warning('No selected File')
        return jsonify({'message': "No selected file"}), HTTPStatus.BAD_REQUEST

    filename: str = file.filename

    filename_split: [] = filename.split('.')

    if not (filename_split[-1] == constants.VALID_EXTENSIONS_XLS or
            filename_split[-1] == constants.VALID_EXTENSIONS_XLSX):
        logging.warning(f'{filename_split[-1]} is not a valid extension')
        return {
            'message': f'{filename_split[-1]} is not a valid extension'}, 420

    # Read sheets names as country name
    if filename_split[-1] == constants.VALID_EXTENSIONS_XLSX:
        sheets: dict = pd.read_excel(file, None, engine='openpyxl')
    else:
        sheets: dict = pd.read_excel(file, None)

    logging.debug(sheets)

    # For Each sheet
    for country_name in sheets:
        try:
            # If country exist take id, else, create a new country and take the
            # new id
            country: PriceCountry = PriceCountry.query \
                .filter(PriceCountry.name == country_name.upper()) \
                .first()

            country_id: int
            if country is None:
                country = PriceCountry()
                country.name = country_name.upper()
                country.code = country_name.upper()
                db.session.add(country)
                db.session.commit()

            country_id = country.id

        except Exception as exp:
            logging.error(f"Error in database {exp}")
            db.session.rollback()
            return jsonify({'message': f"Error in database {exp}"}), 500

        modules_hash = {}
        category_hash = {}
        subcategory_hash = {}

        last_category_name = None
        category_low_value = 0
        category_medium_value = 0
        category_high_value = 0

        for row in sheets[country_name].iterrows():
            if row[1][constants.ROW_PRE] != 'BASE':
                # Read Column "MODULO" and find Module by name
                module_name = row[1][constants.ROW_MODULO]
                if module_name not in modules_hash:
                    logging.debug(module_name)
                    module: PriceModule = PriceModule.query.filter(
                        PriceModule.name == module_name).first()
                    if module is None:
                        try:
                            module = PriceModule()
                            module.name = module_name
                            db.session.add(module)
                            db.session.commit()
                            modules_hash[module_name] = module

                        except Exception as exp:
                            logging.error(f"Database error. {exp}")
                            db.session.rollback()
                            return jsonify({'message': f"Database error. {exp}"}), 500
                    else:
                        modules_hash[module_name] = module
                else:
                    module: PriceModule = PriceModule.query.filter(
                        PriceModule.name == module_name).first()

                # Read Column "PARAMETRO" and find a "PriceCategory"
                category_name = row[1][constants.ROW_PARAMETRO]
                if not last_category_name is None and last_category_name != category_name:
                    last_category = category_hash[last_category_name]
                    try:
                        value = PriceValue.query.filter(
                            PriceValue.module_id == modules_hash[module_name].id) .filter(
                            PriceValue.country_id == country_id) .filter(
                            PriceValue.category_id == last_category.id) .first()
                    except Exception as exp:
                        logging.error(f"Database error {exp}")
                        return jsonify({'message': f"Database error {exp}"}), 500

                    if value is None:
                        value = PriceValue()
                        try:
                            country.values.append(value)
                            db.session.commit()
                            last_category.values.append(value)
                            db.session.commit()
                            module.values.append(value)
                            db.session.commit()
                        except Exception as exp:
                            logging.error(f"Database error {exp}")
                            return jsonify({'message': f"Database error {exp}"}), 500
                    
                    value.low = category_low_value
                    value.medium = category_medium_value
                    value.high = category_high_value

                    category_low_value = 0
                    category_medium_value = 0
                    category_high_value = 0

                if category_name not in category_hash:
                    category: PriceCategory = PriceCategory.query \
                        .filter(PriceCategory.name == category_name) \
                        .first()

                    # If PriceCategory exist get id else create and get the id.
                    if category is None:
                        try:
                            category = PriceCategory()
                            category.name = category_name
                            category.code = category_name
                            db.session.add(category)
                            db.session.commit()
                            category_hash[category_name] = category

                        except Exception as exp:
                            logging.error(f'Database error. {exp}')
                            db.session.rollback()
                            return jsonify({'message': f"Database error. {exp}"}), 500
                    else:
                        category_hash[category_name] = category
                else:
                    category: PriceCategory = PriceCategory.query \
                            .filter(PriceCategory.name == category_name) \
                            .first()

                subcategory_name = row[1][constants.ROW_DETALLE]
                if subcategory_name not in subcategory_hash:
                    subcategory: PriceCategory = PriceCategory.query \
                        .filter(PriceCategory.code == subcategory_name) \
                        .filter(PriceCategory.parent_category_id == category.id) \
                        .first()

                    # If PriceCategory exist get id else create and get the id.
                    if subcategory is None:
                        try:
                            subcategory = PriceCategory()
                            subcategory.name = ' '.join(subcategory_name.split(' ')[1:])
                            subcategory.code = subcategory_name
                            category.subcategories.append(subcategory)
                            db.session.add(subcategory)
                            db.session.commit()
                            subcategory_hash[subcategory_name] = subcategory

                        except Exception as exp:
                            logging.error(f'Database error. {exp}')
                            db.session.rollback()
                            return jsonify({'message': f"Database error. {exp}"}), 500
                    else:
                        subcategory_hash[subcategory_name] = subcategory
                else:
                    subcategory: PriceCategory = PriceCategory.query \
                        .filter(PriceCategory.code == subcategory_name) \
                        .filter(PriceCategory.parent_category_id == category.id) \
                        .first()
                # Read columns "ESTANDAR BAJO", "ESTANDAR MEDIO", "ESTANDAR ALTO".
                try:
                    low: float = row[1][constants.ROW_BAJO]
                    medium: float = row[1][constants.ROW_MEDIO]
                    high: float = row[1][constants.ROW_ALTO]

                except Exception as exp:
                    msg = f"Error reading rows: {constants.ROW_BAJO}, " \
                        f"{constants.ROW_MEDIO}, {constants.ROW_ALTO}: {exp}"
                    logging.error(msg)
                    return jsonify({"message": msg}), 421

                # Get a price value by PriceCountry, PriceCategory and PriceModule. If Exist
                # get Object else, create a new object. Update or create the values
                # low, medium and high.
                module_id = modules_hash[module_name].id
                subcategory_id = subcategory_hash[subcategory_name].id

                module = modules_hash[module_name]
                subcategory = subcategory_hash[subcategory_name]

                try:
                    value = PriceValue.query.filter(
                        PriceValue.module_id == module_id) .filter(
                        PriceValue.country_id == country_id) .filter(
                        PriceValue.category_id == subcategory_id) .first()
                except Exception as exp:
                    logging.error(f"Database error {exp}")
                    return jsonify({'message': f"Database error {exp}"}), 500

                if value is None:
                    value = PriceValue()
                    try:
                        country.values.append(value)
                        db.session.commit()
                        subcategory.values.append(value)
                        db.session.commit()
                        module.values.append(value)
                        db.session.commit()
                    except Exception as exp:
                        logging.error(f"Database error {exp}")
                        return jsonify({'message': f"Database error {exp}"}), 500

                category_low_value += low
                category_medium_value += medium
                category_high_value += high

                value.low = low
                value.medium = medium
                value.high = high
                
                last_category_name = category_name
            else:
                base_name = row[1][constants.ROW_MODULO]
                if base_name not in category_hash:
                    category: PriceCategory = PriceCategory.query \
                        .filter(PriceCategory.name == base_name) \
                        .first()

                    # If PriceCategory exist get id else create and get the id.
                    if category is None:
                        try:
                            category = PriceCategory()
                            category.name = base_name
                            category.code = 'BASE'
                            db.session.add(category)
                            db.session.commit()
                            category_hash[base_name] = category

                        except Exception as exp:
                            logging.error(f'Database error. {exp}')
                            db.session.rollback()
                            return jsonify({'message': f"Database error. {exp}"}), 500
                    else:
                        category_hash[base_name] = category
                else:
                    category: PriceCategory = PriceCategory.query \
                            .filter(PriceCategory.name == base_name) \
                            .first()
                try:
                    low: float = row[1][constants.ROW_BAJO]
                    medium: float = row[1][constants.ROW_MEDIO]
                    high: float = row[1][constants.ROW_ALTO]

                except Exception as exp:
                    msg = f"Error reading rows: {constants.ROW_BAJO}, " \
                        f"{constants.ROW_MEDIO}, {constants.ROW_ALTO}: {exp}"
                    logging.error(msg)
                    return jsonify({"message": msg}), 421

                # Get a price value by PriceCountry, PriceCategory and PriceModule. If Exist
                # get Object else, create a new object. Update or create the values
                # low, medium and high.

                try:
                    value = PriceValue.query.filter(
                        PriceValue.country_id == country_id) .filter(
                        PriceValue.category_id == category.id) .first()
                except Exception as exp:
                    logging.error(f"Database error {exp}")
                    return jsonify({'message': f"Database error {exp}"}), 500

                if value is None:
                    value = PriceValue()
                    try:
                        country.values.append(value)
                        db.session.commit()
                        category.values.append(value)
                        db.session.commit()
                    except Exception as exp:
                        logging.error(f"Database error {exp}")
                        return jsonify({'message': f"Database error {exp}"}), 500

                value.low = low
                value.medium = medium
                value.high = high

            # commit database
            try:
                db.session.commit()
            except Exception as exp:
                db.session.rollback()
                logging.error(f"Database error {exp}")
                return jsonify({'message': f"Database error {exp}"}), 500

    # Return status
    return jsonify({'status': 'OK'})


@app.route('/api/prices/create', methods=['GET'])
def get_categories():
    """
        Get Categories
        ---
        tags:
        - "Prices"
        produces:
        - "application/json"
        responses:
            200:
              description: Categories
            500:
              description: Database or Internal Server error
    """
    try:
        # Query all Categories en DB.
        categories: [] = PriceCategory.query.all()
        countries: [] = PriceCountry.query.all()

    except Exception as exp:
        logging.error(f"Database error {exp}")
        return jsonify({'message': f"Database error {exp}"}), 500

    cat: PriceCategory
    return jsonify({
        'categories': [cat.to_dict() for cat in categories],
        'countries': [country.to_dict() for country in countries]
    })


@app.route('/api/prices', methods=['POST'])
@token_required
def get_estimated_price():
    """
        Get Estimated price
        ---

        tags:
        - "Prices"
        produces:
        - "application/json"
        consumes:
        - "application/json"
        parameters:
        - in: "body"
          name: "body"
          required:
          - categories
          - workspaces
          - country
          properties:
            categories:
                type: array
                items:
                    type: object
                    properties:
                        id:
                            type: integer
                            description: Unique id
                        code:
                            type: string
                            description: Category code

                        name:
                            type: string
                            description: Category Name
                        type:
                            type: string
                            description: Type of question ('A' or 'B')
                        resp:
                            type: string
                            description: Response for this category
                            enum: [low, normal, high]
            workspaces:
                type: array
                items:
                    type: object
                    properties:
                        id:
                            type: integer
                            description: Unique id
                        m2_gen_id:
                            type: integer
                            description: m2_gen_id
                        observation:
                            type: integer
                            description: observation
                        quantity:
                            type: integer
                            description: quantity
                        space_id:
                            type: integer
                            description: space_id
            country:
                type: string
            m2:
                type: number
                format: float

    """
    # Check JSON Input
    params = {
        'categories',
        'workspaces',
        'country',
        'm2'
    }

    for param in params:
        if param not in request.json:
            logging.error(f'{param} not in body')
            return jsonify({'message': f'{param} not in body'}), \
                HTTPStatus.BAD_REQUEST

    try:
        workspaces: [] = request.json['workspaces']
        categories: [] = request.json['categories']

    except Exception as exp:
        logging.error(exp)
        return {'message': f'{exp}'}, \
            HTTPStatus.BAD_REQUEST

    spaces = {}

    # Get all spaces.
    token = request.headers.get('Authorization', None)
    for _space in workspaces:
        try:
            headers = {'Authorization': token}
            resp = requests.get(
                f'http://{SPACES_MODULE_HOST}:{SPACES_MODULE_PORT}{SPACES_MODULE_API}'
                f'/{_space["space_id"]}', headers=headers)
            space = json.loads(resp.content.decode('utf-8'))
            spaces[space['id']] = space['name']

        except Exception as exp:
            logging.error(f"Error getting spaces {exp}")
            return f"Error getting spaces {exp}", 500

    # ---------------- Calc total price -------------------------
    # Get Country id
    country_name = request.json['country']
    country: PriceCountry = PriceCountry.query.filter(
        PriceCountry.name == country_name).first()
    if country is None:
        return f'{country_name} is a invalid country'

    # Find prices according to space
    space_category_prices = {}
    #for _space in workspaces:
    i=0
    while i<len(workspaces):
        space_name = spaces[workspaces[i]['space_id']]
        # Get PriceModule id
        price_module: PriceModule = PriceModule.query.filter(
            PriceModule.name == space_name).first()
        if price_module is None:
            logging.warning(f'No space name: {space_name}')
            workspaces.remove(workspaces[i])
            i=i-1
        else:
            # Get all prices and save in a map:
            prices = PriceValue.query.filter(PriceValue.country_id == country.id) \
                .filter(PriceValue.module_id == price_module.id)
            category_prices = {}
            price: PriceValue

            for price in prices:
                category_prices[price.category_id] = {
                    'low': price.low,
                    'normal': price.medium,
                    'high': price.high
                }

            space_category_prices[workspaces[i]['space_id']] = category_prices
        i=i+1

    final_value = 0
    m2 = request.json['country']
    weeks = get_project_weeks(m2, token)
    # iterate in categories and find prices
    for category in categories:
        cat_id = category['id']
        cat_resp = category['resp']
        cat_name = category['name']
        for _space in workspaces:
            space_id = _space['space_id']
            if space_id in space_category_prices:
                if category['code'] != 'BASE':
                    final_value += (space_category_prices[space_id]
                                [cat_id][cat_resp]) * _space['quantity']
                else:
                    calc_type = constants.BASES_CALC[cat_name]
                    calc_type = calc_type.split('/')
                    calc_type = calc_type[0]
                    div_factor = 1
                    if len(calc_type) > 1:
                        div_factor = calc_type[1]

                    if calc_type == 'm2':
                        final_value += (space_category_prices[space_id]
                                [cat_id][cat_resp]*(m2/div_factor)) * _space['quantity']
                    elif calc_type == 'weeks':
                        final_value += (space_category_prices[space_id]
                                [cat_id][cat_resp]*weeks) * _space['quantity']
                    else:
                        final_value += (space_category_prices[space_id]
                                [cat_id][cat_resp]) * _space['quantity']
            else:
                logging.warning(f"Not valid space_id: {_space['space_id']}")

    # Add Base costs
    # TODO: Agregar nuevas formulas de calculo de base
    '''base_value: PriceValue = PriceValue.query.filter(
        PriceModule.name == 'BASE').first()
    if base_value is None:
        logging.error("Check Base Values")
        return jsonify({'value': final_value})
    final_value += base_value.medium'''

    return jsonify({'value': final_value})


if __name__ == '__main__':
    app.run(host=APP_HOST, port=APP_PORT, debug=True)
