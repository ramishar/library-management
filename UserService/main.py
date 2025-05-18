from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import os
import pika
import json
# from datetime import date

rabbitmq_user = os.getenv("RABBITMQ_USER")
rabbitmq_pass = os.getenv("RABBITMQ_PASS")

credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_pass)
connection = pika.BlockingConnection(pika.ConnectionParameters("rabbitmq", 5672, "/", credentials))
channel = connection.channel()

db_user = os.getenv('POSTGRES_USER')
db_password = os.getenv('POSTGRES_PASSWORD')
db_host = os.getenv('POSTGRES_HOST')
db_port = os.getenv('POSTGRES_PORT')
db_name = os.getenv('POSTGRES_DB')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = 'users'

    studentid = db.Column(db.String(20), primary_key=True)
    firstname = db.Column(db.String(50), nullable=False)
    lastname = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    
    def to_dict(self):
        return {
            "studentid": self.studentid,
            "firstname": self.firstname,
            "lastname": self.lastname,
            "email": self.email
        }
with app.app_context():
    db.create_all()


# CREATE users
@app.route('/users/add', methods=['POST'])
def create_user():
    data = request.json
    user = User(
         studentid=data['studentid'], 
         firstname=data['firstname'],
         lastname=data['lastname'], 
         email=data['email']
    )
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


# READ all users
@app.route('/users/all', methods=['GET'])
def get_users():
    users = User.query.all()
    return jsonify([user.to_dict() for user in users]), 200


# READ a single user by ID
@app.route('/users/<studentid>', methods=['GET'])
def get_user(studentid:str):
    user = User.query.get(studentid)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict()), 200


# UPDATE a user by student_id
@app.route('/users/<studentid>', methods=['PUT'])
def update_user(studentid:str):
    user = User.query.get(studentid)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.json
    if 'firstname' in data:
        user.firstname = data['firstname']
    if 'lastname' in data:
        user.lastname = data['lastname']
    if 'email' in data:
        # Check if new email already exists for another user
        if User.query.filter(User.email == data['email'], User.studentid != studentid).first():
            return jsonify({"error": "Email already exists"}), 400
        user.email = data['email']
    db.session.commit()
    return jsonify(user.to_dict()), 200


# DELETE a user by student_id
@app.route('/users/<studentid>', methods=['DELETE'])
def delete_user(studentid:str):
    user = User.query.get(studentid)
    if not user:
        return jsonify({"error": "User not found"}), 404

    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted successfully"}), 200

@app.route('/users/borrow/request', methods=['POST'])
def borrow_book():
    data = request.get_json()
    required_fields = {'studentid', 'book_id', 'return_date'}
    if not data or not required_fields.issubset(data.keys()):
        return jsonify({"error":"Invalid data format"}), 400

    channel.basic_publish(exchange='', routing_key='borrow_book', body=json.dumps(data))

    return jsonify({"message": "Borrow request successfully posted", "request": data}), 201


if __name__ == "__main__":
	app.run(host="0.0.0.0", port=5002)
