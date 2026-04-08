# OPS_Mongo

A small Flask-based order processing system using MongoDB as the backend database.

## Overview

This application is a simple order management system that supports:

- Customer listing and summary
- Product listing, add, delete, and stock updates
- Placing orders for customers
- Viewing orders by customer
- Viewing order details
- Cancelling orders
- Customer spending and order summary

## Tech Stack

- Python 3.12
- Flask
- PyMongo
- MongoDB
- Jinja2 templates

## Project Structure

- `app.py` - main Flask application
- `templates/` - HTML templates used by the Flask app
- `opsmdb/` - Python virtual environment included in the workspace

## Requirements

- MongoDB running locally at `mongodb://localhost:27017/`
- Python 3.12
- Flask and PyMongo installed in the virtual environment

## Setup

1. Activate the virtual environment:

   ```powershell
   cd c:\Users\harsh\Desktop\OPS_Mongo\OPS_Mongo
   .\opsmdb\Scripts\Activate.ps1
   ```

2. Install dependencies if needed:

   ```powershell
   pip install flask pymongo
   ```

3. Start MongoDB locally.

4. Run the Flask app:

   ```powershell
   python app.py
   ```

5. Open the app in your browser:

   ```text
   http://127.0.0.1:5000/
   ```

## Database

The app uses a MongoDB database named `order_process_sys`.

Collections used:

- `customers`
- `products`
- `orders`

### Expected document fields

Customers:

- `_id`
- `CustomerID`
- `Name`
- `Email`
- `Phone`

Products:

- `_id`
- `product_name`
- `price`
- `stock`

Orders:

- `_id`
- `customer_id` (ObjectId reference to customers)
- `orderDate`
- `status`
- `items` (array with product details, quantity, and price)

## App Routes

- `/` - home page
- `/customers` - list customers
- `/products` - list products
- `/place_order` - create a new order
- `/orders/<customer_id>` - list orders for a customer
- `/order/<order_id>` - order details
- `/cancel_order/<order_id>` - cancel an order
- `/customer_summary` - summary of customer orders and spending

## API Endpoints

- `POST /add_customer` - add a new customer
- `POST /add_product` - add a new product
- `POST /delete_product` - delete a product
- `POST /update_stock` - update product stock

## Notes

- The application expects MongoDB to be available at `localhost:27017`.
- If MongoDB is unavailable, the app exits with a connection error.
- The app runs in debug mode by default when launched from `app.py`.

## Improvements

Possible enhancements:

- Add authentication
- Add input validation in templates
- Add a `requirements.txt`
- Add database migration or seeding scripts
- Add unit tests
