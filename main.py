import enum
import logging
import os
import jwt
import json
import pandas as pd
import pprint
import requests
import datetime as dt
from flask import Flask, jsonify, abort, request
from functools import wraps
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_swagger import swagger
from flask_swagger_ui import get_swaggerui_blueprint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import SQLAlchemyError
from http import HTTPStatus
from xlrd import XLRDError

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

M2_MODULE_HOST = os.getenv('M2_MODULE_HOST', '127.0.0.1')
M2_MODULE_PORT = os.getenv('M2_MODULE_PORT', 5001)
M2_MODULE_API = os.getenv('M2_MODULE_API', '/api/m2')
M2_URL = f"http://{M2_MODULE_HOST}:{M2_MODULE_PORT}"

CURRENCY_ID = "7669e0abe994488f808bf18d8b310e02"

EXCHANGE_BASE_URL = "openexchangerates.org/api/"
EXCHANGE_CURRENCY_URL = f"https://{EXCHANGE_BASE_URL}currencies.json"
EXCHANGE_STATE_URL =    f"https://{EXCHANGE_BASE_URL}usage.json?app_id={CURRENCY_ID}"
EXCHANGE_RATE_URL =     f"https://{EXCHANGE_BASE_URL}latest.json?app_id={CURRENCY_ID}"



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
        'app_name': "WYS API - Prices Service"
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
    type = db.Column(db.CHAR, nullable=False)
    parent_category_id = db.Column(db.Integer, db.ForeignKey('price_category.id'))
    subcategories = db.relationship("PriceCategory",
                                    backref=db.backref(
                                        'price_category', remote_side=[id]),
                                    cascade="all, delete, delete-orphan"
                                    )
    values = db.relationship("PriceValue",
                             backref="price_category",
                             cascade="all, delete, delete-orphan")

    def to_dict(self, full=False):
        obj_dict = {
            'id': self.id,
            'code': self.code,
            'type': self.type,
            'name': self.name
        }

        if full:
            obj_dict['parent_category_id'] = self.parent_category_id
            obj_dict['subcategories'] = [subcategory.to_dict()
                                         for subcategory in self.subcategories]
        return obj_dict

    def serialize(self, full=False):
        return jsonify(self.to_dict(full))


class PriceGen(db.Model):
    """
    id:  Id primary key
    project_id: Project ID that you want to save this configurations
    value: Value of the PROJECT
    m2: M2 of the project
    """

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False, unique=True)
    value = db.Column(db.Float, nullable=False, default=0.0)
    m2 = db.Column(db.Float, nullable=False, default=0.0)
    relations = db.relationship("PriceGenHasPriceValue",
                                backref=db.backref(
                                    'price_gen_has_price_value', remote_side=[id]),
                                cascade="all, delete, delete-orphan")

    def to_dict(self, full=True):
        """
        Convert to dictionary
        """
        obj_dict = {
            'project_id': self.project_id,
            'value': self.value,
            'm2': self.m2
        }
        if full:
            obj_dict['price_value_saved'] = [relation.to_dict()
                                             for relation in self.relations]

        return obj_dict

    def serialize(self, full):
        return jsonify(self.to_dict())


class PriceDesign(db.Model):
    """
    id: Id primary key
    category_1: Value in USD related to a base cost of a 100 m2 or less space
    category_2: Value in USD related to a base cost of a space between 100 and 500 m2
    category_3: Value in USD related to a base cost of a space between 500 and 1000 m2
    category_4: Value in USD related to a base cost of a space between 1000 and 2500 m2
    category_5: Value in USD related to a base cost of a 2500 m2 or more space
    """
    id = db.Column(db.Integer, primary_key=True)
    category_1 = db.Column(db.Float, nullable=False, default=0.0)
    category_2 = db.Column(db.Float, nullable=False, default=0.0)
    category_3 = db.Column(db.Float, nullable=False, default=0.0)
    category_4 = db.Column(db.Float, nullable=False, default=0.0)
    category_5 = db.Column(db.Float, nullable=False, default=0.0)
    country_id = db.Column(
        db.Integer,
        db.ForeignKey('price_country.id'),
        nullable=False)


class PriceGenHasPriceValue(db.Model):
    """
    id: Id primary key
    price_gen_id: ID related to the project's value generated
    price_value_id: ID related to the item (category, module, country) in price_value
    price_value_option_selected: option selected: low, high, mediu
    """
    id = db.Column(db.Integer, primary_key=True)
    price_gen_id = db.Column(
        db.Integer,
        db.ForeignKey('price_gen.id'),
        nullable=False)
    price_value_id = db.Column(
        db.Integer,
        db.ForeignKey('price_value.id'),
        nullable=False)
    price_value_option_selected = db.Column(db.String(45), nullable=False)
    prices_value = db.relationship("PriceValue",
                                   backref=db.backref(
                                       'price_value', remote_side=[price_value_id]),
                                   cascade="all, delete, delete-orphan",
                                   single_parent=True)

    def to_dict(self, full=True):
        """
        Convert to dictionary
        """
        obj_dict = {
            'price_value_id': self.price_value_id,
            'price_value_option_selected': self.price_value_option_selected
        }
        if(full):
            obj_dict['price_value_detail'] = [self.prices_value.to_dict()]

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

    def to_dict(self, only_name=False):
        obj_dict = {}
        if only_name == False:
            obj_dict['id'] = self.id
            obj_dict['default'] = self.default
        obj_dict['name'] = self.name
        return obj_dict


class PriceValue(db.Model):
    """
    id: Id primary key
    low: 
    medium: 
    high:
    module_id:
    country_id:
    category_id:
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
        nullable=False)
    category_id = db.Column(
        db.Integer,
        db.ForeignKey('price_category.id'),
        nullable=False)
    country_name = db.relationship("PriceCountry",
                                   backref="price_country",
                                   remote_side="PriceValue.country_id",
                                   cascade="all, delete, delete-orphan",
                                   single_parent=True)

    def to_dict(self):
        """
        Convert to dictionary
        """
        obj_dict = {
            'module_id': self.module_id,
            'country_id': self.country_id,
            'category_id': self.category_id,
            'country_name': self.country_name.to_dict(only_name=True)
        }

        return obj_dict

    def serialize(self):
        return jsonify(self.to_dict())


class ExchangeRates(db.Model):
    """
    id: Currency code
    rate: Currency rate with base USD
    """
    id = db.Column(db.String(3), nullable=False, primary_key=True)
    rate = db.Column(db.Float, nullable=False, default=0.0)

    def to_dict(self):
        """
        Convert to dictionary
        """
        obj_dict = {
            'rate_id': self.id,
            'rate_value': self.rate
        }

        return obj_dict

    def serialize(self):
        return jsonify(self.to_dict())


class ExchangeRateTimeStamp(db.Model):
    """
    id: Identifier, there is only one row with index 1.
    lastUpdate: TimeStamp of the last time that ExchangeRates was updated.
    """

    id = db.Column(db.Integer, primary_key=True)
    lastUpdate = db.Column(db.DateTime, nullable=False, default=dt.datetime(1970,1,1))

    def to_dict(self):
        """
        Convert to dictionary
        """
        obj_dict = {
            'rate_id': self.id,
            'lastUpdate': self.lastUpdate
        }

        return obj_dict

    def serialize(self):
        return jsonify(self.to_dict())


db.create_all()
db.session.commit()


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


@app.route('/api/prices/design/upload', methods=['POST'])
@token_required
def upload_design_prices():
    """
        Upload/Update Design Prices
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
    try:
        ''' Verify that archive is a Excel spreadsheet (xls or xlsx)'''
        # Check if the post request has the file part
        if 'file' not in request.files:
            abort(HTTPStatus.BAD_REQUEST, "No Multipart file found")
        file = request.files['file']

        if file.filename == '':
            logging.warning('No selected File')
            return jsonify({'message': "No selected file"}), HTTPStatus.BAD_REQUEST

        filename: str = file.filename

        filename_split: list = filename.split('.')
        if not (filename_split[-1] == constants.VALID_EXTENSIONS_XLS or
                filename_split[-1] == constants.VALID_EXTENSIONS_XLSX):
            logging.warning(f'{filename_split[-1]} is not a valid extension')
            return {
                'message': f'{filename_split[-1]} is not a valid extension'}, 420

        # Read sheets names as country name

        if filename_split[-1] == constants.VALID_EXTENSIONS_XLSX:
            sheets: dict = pd.read_excel(file.read(), None, engine='openpyxl')
        else:
            sheets: dict = pd.read_excel(file.read(), None)

        logging.debug(sheets)

        country_design_prices = {}

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

            if country_id not in country_design_prices:
                country_design_prices[country_id] = []

            for row in sheets[country_name].iterrows():
                # Read Column B and finds out the price design category
                try:
                    design_category = row[1][1]
                    price_design_category = float(row[1][2])

                    country_design_prices[country_id].append(
                        [design_category, price_design_category])

                except Exception as exp:
                    msg = f"Error reading rows: {exp}"
                    logging.error(msg)
                    return jsonify({"message": msg}), 421

            # Get a price design by PriceCountry. If Exist get Object else,
            # create a new object. Update or create the values category_1,...,category_5.

            try:
                qr = PriceDesign.query.filter(
                    PriceDesign.country_id == country_id) .first()
            except Exception as exp:
                logging.error(f"Database error {exp}")
                return jsonify({'message': f"Database error {exp}"}), 500

            if qr is None:
                try:
                    qr = PriceDesign()
                    qr.country_id = country_id
                    db.session.add(qr)
                    db.session.commit()
                except Exception as exp:
                    logging.error(f'Database error. {exp}')
                    db.session.rollback()
                    return jsonify({'message': f"Database error. {exp}"}), 500

            for category, value in country_design_prices[country_id]:
                if category == constants.CATEGORY_1:
                    qr.category_1 = value
                if category == constants.CATEGORY_2:
                    qr.category_2 = value
                if category == constants.CATEGORY_3:
                    qr.category_3 = value
                if category == constants.CATEGORY_4:
                    qr.category_4 = value
                if category == constants.CATEGORY_5:
                    qr.category_5 = value

            # commit database
            try:
                db.session.commit()
            except Exception as exp:
                db.session.rollback()
                logging.error(f"Database error {exp}")
                return jsonify({'message': f"Database error {exp}"}), 500

        # Return status
        return jsonify({'status': 'OK'})
    except SQLAlchemyError as e:
        return f'Database error  f{e}', 500
    except XLRDError as exc:
        return f'Excel file error  f{exc}', 500
    except Exception as exp:
        app.logger.error(f"Error: mesg ->{exp}")
        return jsonify({'message': exp}), 500


@app.route('/api/prices/upload', methods=['POST'])
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

    ''' Verify that archive is a Excel spreadsheet (xls or xlsx)'''
    # Check if the post request has the file part
    if 'file' not in request.files:
        abort(HTTPStatus.BAD_REQUEST, "No Multipart file found")
    file = request.files['file']

    if file.filename == '':
        logging.warning('No selected File')
        return jsonify({'message': "No selected file"}), HTTPStatus.BAD_REQUEST

    filename: str = file.filename

    filename_split: list = filename.split('.')

    if not (filename_split[-1] == constants.VALID_EXTENSIONS_XLS or
            filename_split[-1] == constants.VALID_EXTENSIONS_XLSX):
        logging.warning(f'{filename_split[-1]} is not a valid extension')
        return {
            'message': f'{filename_split[-1]} is not a valid extension'}, 420

    # Read sheets names as country name
    if filename_split[-1] == constants.VALID_EXTENSIONS_XLSX:
        sheets: dict = pd.read_excel(file.read(), None, engine='openpyxl')
    else:
        sheets: dict = pd.read_excel(file.read(), None)

    logging.debug(sheets)

    flag = False
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
        last_category_is_base = None
        #same_category_cycle = False
        category_low_value = 0
        category_medium_value = 0
        category_high_value = 0

        for row in sheets[country_name].iterrows():
            is_base = False
            if row[1][constants.ROW_PRE] == 'BASE':
                is_base = True
            if last_category_is_base is None:
                last_category_is_base = is_base
            # Carga de costos variables
            # Read Column "MODULO" and find Module by name
            if not is_base:
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
            category_name = row[1][constants.ROW_MODULO] if is_base else row[1][constants.ROW_PARAMETRO]
            # finding if it's type A or B
            if len(category_name.split('(')) > 1:
                category_type = 'B'
            else:
                category_type = 'A'

            '''
            if  last_category_name != category_name and same_category_cycle == True:
                print(last_category_name,last_category.id)
                same_category_cycle = False
                last_category_name = None
                category_low_value = 0
                category_medium_value = 0
                category_high_value = 0
            '''
            if not last_category_name is None and last_category_name != category_name:
                last_category = category_hash[last_category_name]
                # print(last_category.id)
                try:
                    if is_base:
                        value = PriceValue.query.filter(
                            PriceValue.country_id == country_id) .filter(
                            PriceValue.category_id == last_category.id) .first()
                    else:
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
                        if not last_category_is_base:
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
            '''
            else:
                #setting a flag, to reset last_category_name to None if the cycle with categories is done
                if last_category_name == category_name and last_category_name is not None:
                    same_category_cycle = True
            '''
            if category_name not in category_hash:
                category: PriceCategory = PriceCategory.query \
                    .filter(PriceCategory.name == category_name) \
                    .first()

                # If PriceCategory exist get id else create and get the id.
                if category is None:
                    try:
                        category = PriceCategory()
                        category.name = category_name
                        category.code = category_name if not is_base else 'BASE'

                        category.type = category_type

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
            subcategory_code = ''
            have_subcat = True
            if pd.isna(subcategory_name):
                have_subcat = False
            if have_subcat:
                if flag:
                    print('have_subcat')
                subcategory_code = category_name + ' ' + subcategory_name
                if subcategory_code not in subcategory_hash:
                    subcategory: PriceCategory = PriceCategory.query \
                        .filter(PriceCategory.name == subcategory_name) \
                        .filter(PriceCategory.parent_category_id == category.id) \
                        .first()

                    # If PriceCategory exist get id else create and get the id.
                    if subcategory is None:
                        try:
                            subcategory = PriceCategory()
                            subcategory.name = subcategory_name
                            subcategory.code = subcategory_code if not is_base else 'BASE'
                            subcategory.type = category_type
                            category.subcategories.append(subcategory)
                            db.session.add(subcategory)
                            db.session.commit()
                            subcategory_hash[subcategory_code] = subcategory

                        except Exception as exp:
                            logging.error(f'Database error. {exp}')
                            db.session.rollback()
                            return jsonify({'message': f"Database error. {exp}"}), 500
                    else:
                        subcategory_hash[subcategory_code] = subcategory
                else:
                    subcategory: PriceCategory = PriceCategory.query \
                        .filter(PriceCategory.name == subcategory_name) \
                        .filter(PriceCategory.parent_category_id == category.id) \
                        .first()
            # Read columns "ESTANDAR BAJO", "ESTANDAR MEDIO", "ESTANDAR ALTO".
            try:
                low: float = row[1][constants.ROW_BAJO] if not pd.isna(row[1][constants.ROW_BAJO]) else 0
                medium: float = row[1][constants.ROW_MEDIO] if not pd.isna(row[1][constants.ROW_MEDIO]) else 0
                high: float = row[1][constants.ROW_ALTO] if not pd.isna(row[1][constants.ROW_ALTO]) else 0

            except Exception as exp:
                msg = f"Error reading rows: {constants.ROW_BAJO}, " \
                    f"{constants.ROW_MEDIO}, {constants.ROW_ALTO}: {exp}"
                logging.error(msg)
                return jsonify({"message": msg}), 421

            # Get a price value by PriceCountry, PriceCategory and PriceModule. If Exist
            # get Object else, create a new object. Update or create the values
            # low, medium and high.
            module_id = modules_hash[module_name].id if not is_base else None
            subcategory_id = subcategory_hash[subcategory_code].id if have_subcat else category_hash[category_name].id

            module = modules_hash[module_name] if not is_base else None
            subcategory = subcategory_hash[subcategory_code] if have_subcat else category_hash[category_name]

            try:
                if is_base:
                    value = PriceValue.query.filter(
                        PriceValue.country_id == country_id) .filter(
                        PriceValue.category_id == subcategory_id) .first()
                else:
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
                    if not is_base:
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
            last_category_is_base = is_base
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
@token_required
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
        categories: list = PriceCategory.query.filter(
            PriceCategory.parent_category_id == None).all()
        countries: list = PriceCountry.query.all()

    except Exception as exp:
        logging.error(f"Database error {exp}")
        return jsonify({'message': f"Database error {exp}"}), 500

    cat: PriceCategory
    return jsonify({
        'categories': [cat.to_dict() for cat in categories],
        'countries': [country.to_dict() for country in countries]
    })


@app.route('/api/prices/save', methods=['POST'])
@token_required
def save_prices():
    """
        Save prices
        ---
        tags:
        - Prices
        consumes:
        - "application/json"
        produces:
        - application/json
        required:
            - project_id
            - value
            - country
            - categories
            - workspaces
            - m2
        parameters:
        - in: body
          name: body
          properties:
            project_id:
                type: number
                format: integer
            value:
                type: number
                format: float
            m2:
                type: number
                format: float
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
        responses:
            400:
                description: Data or missing field in body.
            404:
                description: Data object not found.
            500:
                description: Internal server error.
    """

    # Check JSON Input
    params = {
        'categories',
        'country',
        'project_id',
        'value',
        'm2',
        'workspaces'
    }

    for param in params:
        if param not in request.json:
            logging.error(f'{param} not in body')
            return jsonify({'message': f'{param} not in body'}), \
                HTTPStatus.BAD_REQUEST

    try:
        token = request.headers.get('Authorization', None)
        headers = {'Authorization': token}
        resp = requests.get(
            f'{PROJECTS_URL}{PROJECTS_MODULE_API}'
            f'/{request.json["project_id"]}', headers=headers)
        project = json.loads(resp.content.decode('utf-8'))
    except Exception as exp:
        logging.error(f"Error getting Project {exp}")  # cambiar mensaje de exp
        return f"Error getting project {exp}", 500

    # saving PriceGen

    # If PriceGen exist take id, else, create a new PriceGen and take the
    # new id
    price_gen: PriceGen = PriceGen.query \
        .filter(PriceGen.project_id == request.json["project_id"]) \
        .first()

    price_gen_id: int
    try:
        if price_gen is None:
            price_gen = PriceGen()
            price_gen.project_id = request.json["project_id"]

        price_gen.value = request.json["value"]
        price_gen.m2 = request.json["m2"]
        db.session.add(price_gen)
        db.session.commit()

        price_gen_id = price_gen.id

    except Exception as exp:
        logging.error(f"Error in database {exp}")
        db.session.rollback()
        return jsonify({'message': f"Error in database {exp}"}), 500

    # updating project
    project = update_project_by_id(request.json["project_id"], {
                                   'price_gen_id': price_gen_id}, token)
    if project is None:
        return "Cannot update the Project because doesn't exist", 404

    # dictionary lists
    try:
        workspaces: list = request.json['workspaces']
        categories: list = request.json['categories']

    except Exception as exp:
        logging.error(exp)
        return {'message': f'{exp}'}, \
            HTTPStatus.BAD_REQUEST

    spaces = {}
    # Get all spaces.
    for _space in workspaces:
        try:
            token = request.headers.get('Authorization', None)
            headers = {'Authorization': token}
            resp = requests.get(
                f'http://{SPACES_MODULE_HOST}:{SPACES_MODULE_PORT}{SPACES_MODULE_API}'
                f'/{_space["space_id"]}', headers=headers)
            space = json.loads(resp.content.decode('utf-8'))
            spaces[space['id']] = space['name']

        except Exception as exp:
            logging.error(f"Error getting spaces {exp}")
            return f"Error getting spaces {exp}", 500

    # Get Country id
    country_name = request.json['country']
    country: PriceCountry = PriceCountry.query.filter(
        PriceCountry.name == country_name.upper()).first()
    if country is None:
        return f'{country_name} is a invalid country'

     # Find prices according to space

    i = 0
    while i < len(workspaces):
        space_name = spaces[workspaces[i]['space_id']]
        # Get PriceModule id
        price_module: PriceModule = PriceModule.query.filter(
            PriceModule.name == space_name).first()
        if price_module is None:
            logging.warning(f'No module name: {space_name}')
        else:
            # Get specific price and save record relation:
            for category in categories:
                if category['code'] == 'BASE':
                    module_id = None
                else:
                    module_id = price_module.id

                prices = PriceValue.query.filter(PriceValue.country_id == country.id) \
                    .filter(PriceValue.module_id == module_id) \
                    .filter(PriceValue.category_id == category['id']).first()
                if prices is None:
                    logging.warning(
                        f'No price value for category: {category["name"]} and module: {price_module.name}')
                else:
                    pghpv = PriceGenHasPriceValue.query.filter(PriceGenHasPriceValue.price_gen_id == price_gen_id) \
                        .filter(PriceGenHasPriceValue.price_value_id == prices.id).first()

                    try:
                        if pghpv is None:
                            pghpv = PriceGenHasPriceValue()
                            pghpv.price_gen_id = price_gen_id
                            pghpv.price_value_id = prices.id

                        pghpv.price_value_option_selected = category["resp"]
                        db.session.add(pghpv)
                        db.session.commit()
                    except Exception as exp:
                        logging.error(f"Error in database {exp}")
                        db.session.rollback()
                        return jsonify({'message': f"Error in database {exp}"}), 500
        i = i+1

    # Return status
    return jsonify({'status': 'OK'})


def update_project_by_id(project_id, data, token):
    headers = {'Authorization': token}
    api_url = PROJECTS_URL + PROJECTS_MODULE_API + str(project_id)
    rv = requests.put(api_url, json=data, headers=headers)
    if rv.status_code == 200:
        return json.loads(rv.text)
    elif rv.status_code == 500:
        raise Exception("Cannot connect to the projects module")
    return None


def get_workspace_by_project_id(project_id, token):
    headers = {'Authorization': token}
    api_url = M2_URL + M2_MODULE_API + '/' + str(project_id)
    rv = requests.get(api_url, headers=headers)
    if rv.status_code == 200:
        return json.loads(rv.text)
    elif rv.status_code == 500:
        raise Exception("Cannot connect to the m2 module")
    return None


@app.route('/api/prices/load/<project_id>', methods=['GET'])
@token_required
def get_project_prices(project_id):
    """
        Get saved price info info.
        ---
          parameters:
            - in: path
              name: project_id
              type: integer
              description: Saved project ID
          tags:
            - Prices
          responses:
            200:
              description: Saved Price Gen Object, and related Price Value Data Object.
            404:
              description: Project Not Found, it could be an error or it doesn't exists yet.
            500:
              description: Internal Server error or Database error
    """
    resp = {}
    categories = []

    try:
        pricegen = PriceGen.query.filter(
            PriceGen.project_id == project_id).first()
        if pricegen is not None:
            pg_dict = pricegen.to_dict()
            resp['value'] = pg_dict['value']
            resp['m2'] = pg_dict['m2']
            for element in pg_dict['price_value_saved']:
                detail = element['price_value_detail'][0]

                c = {}
                try:
                    category: PriceCategory = PriceCategory.query \
                        .filter(PriceCategory.id == detail['category_id']) \
                        .first()
                    flag = False
                    for dic in categories:
                        if dic['name'] != category.name:
                            flag = True
                        else:
                            flag = False
                    if flag:
                        c['code'] = category.code
                        c['id'] = detail['category_id']
                        c['name'] = category.name
                        c['resp'] = element['price_value_option_selected']
                        c['type'] = category.type
                        resp['country'] = detail['country_name']['name'].lower()
                        categories.append(c)
                except Exception as exp:
                    logging.error(f"Database Exception: {exp}")
                    return f"Database Exception: {exp}", 500

            # Getting workspaces
            token = request.headers.get('Authorization', None)
            project = get_workspace_by_project_id(pg_dict['project_id'], token)

            if(project is not None):
                resp['workspaces'] = project['m2_generated_data']['workspaces']
            else:
                logging.warning(
                    f'No workspaces saved yet: project#{project_id}')
                resp['workspaces'] = []

            resp['categories'] = categories

            if(len(categories) > 0):
                return jsonify(resp), 200
            else:
                return {}, 404
        else:
            return {}, 404
    except Exception as exp:
        logging.error(f"Database Exception: {exp}")
        return f"Database Exception: {exp}", 500


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
                            enum: [A,B]
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
    # total cost in Estimador_de_costo interface
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
        workspaces: list = request.json['workspaces']
        categories: list = request.json['categories']

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
    # for _space in workspaces:
    i = 0

    while i < len(workspaces):
        space_name = spaces[workspaces[i]['space_id']]
        # Get PriceModule id
        price_module: PriceModule = PriceModule.query.filter(
            PriceModule.name == space_name).first()
        if price_module is None:
            logging.warning(f'No space name: {space_name}')
            workspaces.remove(workspaces[i])
            i = i-1
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
        i = i+1

    base_category_prices = {}
    # Get all base prices and save in a map:
    base_prices = PriceValue.query.filter(PriceValue.country_id == country.id) \
        .filter(PriceValue.module_id == None)
    base_price: PriceValue

    for base_price in base_prices:
        base_category_prices[base_price.category_id] = {
            'low': base_price.low,
            'normal': base_price.medium,
            'high': base_price.high
        }
    space_category_prices[-1] = base_category_prices

    final_value = 0
    m2 = request.json['m2']
    weeks = get_project_weeks(m2, token)
    # iterate in categories and find prices
    for category in categories:
        cat_id = category['id']
        cat_resp = category['resp']
        cat_name = category['name']

        if category['code'] != 'BASE':
            for _space in workspaces:
                space_id = _space['space_id']
                if space_id in space_category_prices:
                    final_value += (space_category_prices[space_id]
                                    [cat_id][cat_resp]) * _space['quantity']
                else:
                    logging.warning(
                        f"Not valid space_id: {_space['space_id']}")
        else:
            calc_type = ''
            div_factor = 1
            if cat_name in constants.BASES_CALC:
                calc_type = constants.BASES_CALC[cat_name]
                calc_type = calc_type.split('/')
                if len(calc_type) > 1:
                    div_factor = float(calc_type[1])
                calc_type = calc_type[0]

            if calc_type == 'm2':
                final_value += (space_category_prices[-1]
                                [cat_id][cat_resp]*(m2/div_factor))
            elif calc_type == 'weeks':
                final_value += (space_category_prices[-1]
                                [cat_id][cat_resp]*weeks)
            else:
                final_value += (space_category_prices[-1]
                                [cat_id][cat_resp])

    price_design: PriceDesign = PriceDesign.query.filter(
        PriceDesign.country_id == country.id).first()

    if price_design is not None:
        if m2 < 100:
            final_value += price_design.category_1
        elif 100 <= m2 < 500:
            final_value += price_design.category_2
        elif 500 <= m2 < 1000:
            final_value += price_design.category_3
        elif 1000 <= m2 < 2500:
            final_value += price_design.category_4
        else:
            final_value += price_design.category_5

    return jsonify({'value': final_value}), 200


@app.route('/api/prices/detail', methods=['POST'])
@token_required
def get_estimated_price_detail():
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
        workspaces: list = request.json['workspaces']
        categories: list = request.json['categories']

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
    # for _space in workspaces:
    i = 0
    while i < len(workspaces):
        space_name = spaces[workspaces[i]['space_id']]
        # Get PriceModule id
        price_module: PriceModule = PriceModule.query.filter(
            PriceModule.name == space_name).first()
        if price_module is None:
            logging.warning(f'No space name: {space_name}')
            workspaces.remove(workspaces[i])
            i = i-1
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
        i = i+1

    base_category_prices = {}
    # Get all base prices and save in a map:
    base_prices = PriceValue.query.filter(PriceValue.country_id == country.id) \
        .filter(PriceValue.module_id == None)
    base_price: PriceValue

    for base_price in base_prices:
        base_category_prices[base_price.category_id] = {
            'low': base_price.low,
            'normal': base_price.medium,
            'high': base_price.high
        }
    space_category_prices[-1] = base_category_prices

    final_value = 0
    m2 = request.json['m2']
    weeks = get_project_weeks(m2, token)

    # iterate in categories and find prices
    for category in categories:
        cat_id = category['id']
        cat_resp = category['resp']
        cat_name = category['name']
        cat_obj = PriceCategory.query.filter(
            PriceCategory.name == category['name']).first()
        cat_subcategories = cat_obj.subcategories
        category['subcategories'] = []
        cat_value = 0
        if cat_subcategories:
            for subcat in cat_subcategories:
                subcat_dict = subcat.to_dict()
                subcat_dict['value'] = 0
                subcat_dict['resp'] = cat_resp
                if(category['code'] == 'BASE'):
                    category['subcategories'].append(subcat_dict)

        if category['code'] != 'BASE':
            for _space in workspaces:
                space_id = _space['space_id']
                if space_id in space_category_prices:
                    cat_value += (space_category_prices[space_id]
                                  [cat_id][cat_resp]) * _space['quantity']
                    final_value += cat_value
                    category['value'] = cat_value
                    if cat_subcategories:
                        for subcat in category['subcategories']:
                            subcat['value'] += (space_category_prices[space_id]
                                                [subcat['id']][cat_resp]) * _space['quantity']
                else:
                    logging.warning(
                        f"Not valid space_id: {_space['space_id']}")
        else:
            calc_type = ''
            div_factor = 1
            if cat_name in constants.BASES_CALC:
                calc_type = constants.BASES_CALC[cat_name]
                calc_type = calc_type.split('/')
                if len(calc_type) > 1:
                    div_factor = float(calc_type[1])
                calc_type = calc_type[0]

            if calc_type == 'm2':
                cat_value = (space_category_prices[-1]
                             [cat_id][cat_resp]*(m2/div_factor))
                category['value'] = cat_value
                final_value += cat_value
                if cat_subcategories:
                    for subcat in category['subcategories']:
                        subcat['value'] += (space_category_prices[-1]
                                            [subcat['id']][cat_resp]*(m2/div_factor))
            elif calc_type == 'weeks':
                cat_value = (space_category_prices[-1]
                             [cat_id][cat_resp]*weeks)
                category['value'] = cat_value
                final_value += cat_value
                if cat_subcategories:
                    for subcat in category['subcategories']:
                        subcat['value'] += (space_category_prices[-1]
                                            [subcat['id']][cat_resp]*weeks)
            else:
                cat_value = (space_category_prices[-1]
                             [cat_id][cat_resp])
                category['value'] = cat_value
                final_value += cat_value
                if cat_subcategories:
                    for subcat in category['subcategories']:
                        subcat['value'] += (space_category_prices[-1]
                                            [subcat['id']][cat_resp])

    # do a filter if de value in category is zero
    cat_tmp = []
    for category in categories:
        if category['value'] > 0:
            cat_tmp.append(category)

    categories = cat_tmp

    # getting prices design
    design = {}
    design['name'] = 'COSTOS DISENO'

    pd = PriceDesign.query.filter(
        PriceDesign.country_id == country.id) .first()

    design['value'] = 0
    design['id'] = None

    if pd is not None:
        design['id'] = pd.id

        if m2 < 100:
            design['value'] = pd.category_1
        elif 100 <= m2 < 500:
            design['value'] = pd.category_2
        elif 500 <= m2 < 1000:
            design['value'] = pd.category_3
        elif 1000 <= m2 < 2500:
            design['value'] = pd.category_4
        else:
            design['value'] = pd.category_5

        final_value += design['value']

    resp = {
        'categories': categories,
        'design': design,
        'value': final_value,
        'country': country_name,
        'm2': m2,
        'weeks': weeks
    }
    return jsonify(resp), 200



@app.route('/api/prices/currencies', methods=['GET'])
@token_required
def get_currencies():
    """
        Get Currency Codes
        ---
        tags:
        - "Prices"
        produces:
        - "application/json"
        responses:
            200:
              description: Currency codes used in /api/prices/exchange. They follow the ISO currency codes standard.
            500:
              description: Database or Internal Server error
    """

    rv = requests.get(EXCHANGE_CURRENCY_URL)
    if rv.status_code == 200:
        return json.loads(rv.text), 200

    elif rv.status_code == 500:
        return "Cannot connect to the currency exchange source", 500
    
    return "Database or Internal Server error", 500


def update_exchanges():
    """Update the .. if we have enough requests.
    This function consumes one request, be careful.

    Exceptions:
    - Exception: Currency exchange source requests got exhausted
    - Unbound Exceptions: idk.
    """

    try:
        # Verify remaining requests
        ###########################

        rv_account_state = requests.get(EXCHANGE_STATE_URL)
        account_state = json.loads(rv_account_state.text)

        remaining = account_state["data"]["usage"]["requests_remaining"]

        if remaining < 50:
            raise Exception("Currency exchange source requests got exhausted")

        # Grab data, update table
        #########################

        rv_exchange_rates = requests.get(EXCHANGE_RATE_URL)
        exchange_rates = json.loads(rv_exchange_rates.text)

        new_rates = exchange_rates["rates"]
        old_rates = ExchangeRates.query.all()

        if old_rates:
            old_rates_dict = {rate.id: rate for rate in old_rates}

            for new_key, new_rate in new_rates.items():
                old_rates_dict[new_key].rate = new_rate
                del old_rates_dict[new_key]

            # remaining rates are deleted from db.
            for rate in old_rates_dict.values():
                db.session.delete(rate)

        else:
            for new_key, new_rate in new_rates.items():
                new_item = ExchangeRates()

                new_item.id = new_key
                new_item.rate = new_rate

                db.session.add(new_item)

        db.session.commit()

    except:
        raise


def get_exchange_rate_by_code(code: str):
    """

    Returns:
    - float > 0: the correct rate
    - -1: the code is invalid

    Exception Management:
    - Exception: Problems with database.
    - Unbound Exceptions: idk.
    """

    is_necesary_update = False

    # Update rates if day is over or if there is no data
    ####################################################
    try:
        exchange_state = ExchangeRateTimeStamp.query.get(1)
        last_update = exchange_state.lastUpdate.date()

        if last_update != dt.date.today():
            is_necesary_update = True

    except AttributeError as e:
        first_timestamp = ExchangeRateTimeStamp()
        first_timestamp.lastUpdate = dt.datetime.now()

        db.session.add(first_timestamp)
        db.session.commit()

        is_necesary_update = True

    except Exception as e:
        print (e)
        raise Exception("Problems with database")


    try:
        if is_necesary_update:
            update_exchanges()

    except:
        # unbounds errors.
        raise

    # Grab the data
    ###############

    try:
        exchange_rate = ExchangeRates.query.get(code)
        return exchange_rate.rate

    except AttributeError:
        return -1


@app.route('/api/prices/exchange/<currency_code>', methods=['GET'])
@token_required
def get_currency_exchange(currency_code):
    """
        Get currency exchange according to specified currency_code. 
        The rates are updated every day.
        ---
          parameters:
            - in: path
              name: currency_code
              type: string
              description: Valid currency code specified in ISO standard 4217.
          tags:
            - Prices
          responses:
            200:
              description: Floating point value that represents an exchange rate
            404:
              description: Currency code not found.
            500:
              description: Internal Server error or Database error
    """

    # Obtenemos el factor de cambio, o exchange rate
    # import pudb; pudb.set_trace()

    try:
        rate = get_exchange_rate_by_code(currency_code)
    
        if rate == -1:
            return f"Code {currency_code} is not valid", 404

        resp = {
            "rate": rate
        }

        return jsonify(resp), 200

    except Exception as e:
        return f"Internal error: {e}", 500


## Esto deber??a unirse con el m??todo de arriba, la ??nica diferencia es el m??todo POST y un producto
@app.route('/api/prices/exchange/<currency_code>', methods=['POST'])
@token_required
def get_currency_conversion(currency_code):
    """
        Get currency exchange and conversion according to specified currency_code. 
        When a value is posted, is assumed that is USD.
        The rates are updated every day.
        ---
        parameters:
        - in: "path"
          name: currency_code
          type: string
          description: Valid currency code specified in ISO standard 4217.
        - in: "body"
          name: body
          required:
          - value
          properties:
            value:
                type: number
                description: currency in USD to convert
        tags:
        - "Prices"
        produces:
        - "application/json"
        consumes:
        - "application/json"
        responses:
            200:
              description: Floating point value that represents an exchange rate
            404:
              description: Currency code not found.
            500:
              description: Internal Server error or Database error
    """

    try:
        rate = get_exchange_rate_by_code(currency_code)
    
        if rate == -1:
            return f"Code {currency_code} is not valid", 404

        value = float(request.json["value"])

        resp = {
            "rate": rate,
            "conversion": rate * value
        }

        return jsonify(resp), 200

    except Exception as e:
        return f"Internal error: {e}", 500


if __name__ == '__main__':
    app.run(host=APP_HOST, port=APP_PORT, debug=True)
