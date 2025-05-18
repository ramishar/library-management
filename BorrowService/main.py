
import json
import pika
import os
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from threading import Thread  
import requests

BOOK_SERVICE_URL =  'http://bookservice:5006'

rabbitmq_user = os.getenv('RABBITMQ_USER')
rabbitmq_pass = os.getenv('RABBITMQ_PASS')

# Set up Flask and SQLAlchemy for database interaction
app = Flask(__name__)

db_user = os.getenv('POSTGRES_USER')
db_password = os.getenv('POSTGRES_PASSWORD')
db_host = os.getenv('POSTGRES_HOST')
db_port = os.getenv('POSTGRES_PORT')
db_name = os.getenv('POSTGRES_DB')

app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define database models
class Student(db.Model):
    __tablename__ = 'users'
    studentid = db.Column(db.String(20), primary_key=True)
    firstname = db.Column(db.String(50), nullable=False)
    lastname = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)

class Book(db.Model):
    __tablename__ = 'books'
    book_id = db.Column(db.String(20), primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)

class BorrowRequest(db.Model):
    __tablename__ = 'borrow_requests'
    id = db.Column(db.Integer, primary_key=True)
    studentid = db.Column(db.String(20), db.ForeignKey('users.studentid'), nullable=False)
    book_id = db.Column(db.String(20), db.ForeignKey('books.book_id'), nullable=False)
    return_date = db.Column(db.Date, nullable=False)

    
    def to_dict(self):
        return {
            "studentid": self.studentid,
            "book_id": self.book_id,
            "return_date": self.return_date
        }

# Create tables in the database
with app.app_context():
    db.create_all()

def setup_rabbitmq():
    try:
        credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_pass)
        connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq', 5672, '/', credentials))
        channel = connection.channel()
        channel.queue_declare(queue='borrow_book') 
        return channel
    except pika.exceptions.AMQPConnectionError as e:
        print(f"Error connecting to RabbitMQ: {e}", flush=True)
        return None

# Handle borrow requests from RabbitMQ
def callback(ch, method, properties, body):
    borrow_data = json.loads(body)
    studentid = borrow_data.get('studentid')
    book_id = borrow_data.get('book_id')
    return_date = borrow_data.get('return_date')
    print(borrow_data, flush=True)

    with app.app_context():
        active_borrow_count = (
            db.session.query(BorrowRequest)
            .filter(BorrowRequest.studentid == studentid)
            .count())
    
    print("The active borrow count is: ", active_borrow_count)


    if active_borrow_count >= 5:  
        print(f"Student {studentid} has already borrowed 5 books. Cannot borrow more.", flush=True)
        
        # Send a rejection message to a different queue to notify the sender
        rejection_message = {
            "studentid": studentid,
            "status": "rejected",
            "reason": "Student has already borrowed 5 books."
        }
        ch.basic_publish(
            exchange='',
            routing_key='borrow_book_rejection',  # A rejection queue
            body=json.dumps(rejection_message)
        )
        return 


    borrow_request = BorrowRequest(studentid=studentid, book_id=book_id, return_date=return_date)
    with app.app_context():
        db.session.add(borrow_request)
        db.session.commit()
    print(f"Borrow request saved: Student {studentid} borrowed Book {book_id} until {return_date}", flush=True)

# Start listening for messages from RabbitMQ
def start_borrow_service():
    channel = setup_rabbitmq()
    if channel:
        print('Waiting for borrow requests...', flush=True)
        channel.basic_consume(queue='borrow_book', on_message_callback=callback, auto_ack=True)
        channel.start_consuming()

# Get all books borrowed by a specific user
@app.route('/borrowed_books/<string:studentid>', methods=['GET'])
def get_borrowed_books(studentid):
    books_response = requests.get(f"{BOOK_SERVICE_URL}/books/all", headers={"Content-Type": "application/json"})

    if books_response.status_code != 200:
        return jsonify({"error": "Failed to fetch books from BookService"}), 500
    print("The status code is :",books_response.status_code)
    
    books_data = {book['book_id']: book for book in books_response.json()}
   
    borrowed_records = (
        db.session.query(BorrowRequest.book_id, BorrowRequest.return_date)
        .filter(BorrowRequest.studentid == studentid)
        .all()
    )

    result = []
    for book_id, return_date in borrowed_records:
        book = books_data.get(book_id)
        if book:
            result.append({
                "title": book["title"],
                "author": book["author"],
                "return_date": return_date
            })
        else:
            # Handle cases where book details are not found
            result.append({
                "title": "Unknown",
                "author": "Unknown",
                "return_date": return_date
            })
    
    return jsonify(result)

@app.route('/borrows', methods=['GET'])
def get_all_borrows():
    borrows = BorrowRequest.query.all()
    return jsonify([b.to_dict() for b in borrows]), 200

# Run Flask and RabbitMQ listener concurrently
if __name__ == "__main__":
    Thread(target=start_borrow_service).start()  # Start RabbitMQ listener in a separate thread
    app.run(host='0.0.0.0', port=5007)  # Run Flask app
