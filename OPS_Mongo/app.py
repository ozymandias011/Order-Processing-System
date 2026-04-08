from flask import Flask, render_template, request, redirect, url_for, jsonify
from bson import ObjectId
from bson.errors import InvalidId # Added InvalidId import
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

app = Flask(__name__)

# MongoDB connection
try:
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=5000)
    # Test the connection
    client.admin.command('ping')
    db = client["order_process_sys"]
    print("✅ Successfully connected to MongoDB!")
    print(f"✅ Using database: {db.name}")
    
    # Check if collections exist and show some stats
    collections = db.list_collection_names()
    print(f"📋 Available collections: {collections}")
    
    # Show document counts
    print(f"👥 Customers: {db.customers.count_documents({})}")
    print(f"📦 Products: {db.products.count_documents({})}")
    print(f"📋 Orders: {db.orders.count_documents({})}")
    
except (ConnectionFailure, ServerSelectionTimeoutError) as e:
    print(f"❌ Failed to connect to MongoDB: {e}")
    print("Please ensure MongoDB is running on localhost:27017")
    exit(1)

# Collections
customers_col = db["customers"]
products_col = db["products"]
orders_col = db["orders"]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/customers')
def customers():
    # Include _id by removing {'_id': 0}
    customers = list(db.customers.find({}))
    return render_template('customers.html', customers=customers)

@app.route('/products')
def products():
    products = list(products_col.find())
    return render_template('products.html', products=products)

@app.route('/place_order', methods=['GET', 'POST'])
def place_order():
    customers = list(customers_col.find({}, {"_id": 1, "CustomerID": 1, "Name": 1}))
    # Use product_name to align with database and other template usage
    products = list(products_col.find({}, {"_id": 1, "product_name": 1, "price": 1, "stock": 1}))

    # Debug output
    print(f"🔍 Found {len(customers)} customers")
    print(f"🔍 Found {len(products)} products")
    if customers:
        print(f"🔍 Sample customer: {customers[0]}")

    if request.method == 'POST':
        customer_id = request.form['customer']
        order_items = []

        for key, value in request.form.items():
            if key.startswith('quantity_') and int(value) > 0:
                product_id_str = key.replace('quantity_', '')
                product = None
                try:
                    # First, try to find product by ObjectId
                    product = products_col.find_one({"_id": ObjectId(product_id_str)})
                except InvalidId:
                    # If product_id_str is not a valid ObjectId, try finding by integer _id
                    try:
                        product = products_col.find_one({"_id": int(product_id_str)})
                    except ValueError:
                        # If it's not a valid int either, product will remain None
                        pass
                
                quantity = int(value)
                if not product:
                    return f"Product with ID {product_id_str} not found."
                
                # Robustly get product name for insufficient stock message
                name_candidates_msg = [
                    product.get('product_name'),
                    product.get('productName'),
                    product.get('ProductName')
                ]
                actual_product_name_for_msg = next((name for name in name_candidates_msg if name), "Unknown Product")

                if product['stock'] < quantity:
                    return f"Insufficient stock for product {actual_product_name_for_msg}"

                # Robustly get product name from product document, falling back to "Unnamed Product" if name is empty or not found
                name_candidates = [
                    product.get('product_name'),
                    product.get('productName'),
                    product.get('ProductName')
                ]
                # Find the first non-empty string name, otherwise default
                actual_product_name = next((name for name in name_candidates if isinstance(name, str) and name.strip()), "Unnamed Product")

                # Robustly get product price from product document
                actual_product_price = product.get('price') # Primary
                if actual_product_price is None:
                    actual_product_price = product.get('Price', 0) # Fallback to 'Price' or 0

                order_items.append({
                    "product_id": product['_id'],
                    "productName": actual_product_name, # Stored as 'productName' (capital N)
                    "price": actual_product_price,      # Stored as 'price' (lowercase)
                    "quantity": quantity
                })

        if not order_items:
            return "Please select at least one product with quantity > 0"

        # Insert order - customer_id is already an ObjectId from the form
        order_doc = {
            "customer_id": ObjectId(customer_id),
            "orderDate": datetime.now(),
            "status": "Placed",
            "items": order_items
        }
        orders_col.insert_one(order_doc)

        # Update stock
        for item in order_items:
            products_col.update_one({"_id": item['product_id']}, {"$inc": {"stock": -item['quantity']}})

        return redirect(url_for('list_orders', customer_id=customer_id))

    return render_template('place_order.html', customers=customers, products=products)

@app.route('/orders/<customer_id>')
def list_orders(customer_id): # customer_id is a string from the URL
    orders = []
    customer_doc = None

    try:
        # Attempt to treat customer_id as an ObjectId
        potential_obj_id = ObjectId(customer_id)
        customer_doc = customers_col.find_one({"_id": potential_obj_id})
        if customer_doc:
            # Customer found by _id (ObjectId). Query orders using this ObjectId.
            orders = list(orders_col.find({"customer_id": customer_doc['_id']}).sort("orderDate", -1))
    except InvalidId:
        # customer_id is not a valid ObjectId hex string.
        # Try to treat it as an integer CustomerID.
        try:
            customer_int_id = int(customer_id)
            customer_doc = customers_col.find_one({"CustomerID": customer_int_id})
            if customer_doc:
                # Customer found by CustomerID (int).
                # Orders should be fetched using the customer's _id (ObjectId),
                # as new orders are stored with "customer_id": ObjectId.
                orders = list(orders_col.find({"customer_id": customer_doc['_id']}).sort("orderDate", -1))
        except ValueError:
            # customer_id is not an ObjectId string and also not an integer string.
            # customer_doc remains None, orders remains [].
            pass
    
    return render_template('list_orders.html', orders=orders, customer=customer_doc)

@app.route('/order/<order_id>')
def order_details(order_id): # Parameter name matches the route
    order_doc = None # Use a different variable name for the fetched order
    
    # Attempt to find the order by various ID formats for the incoming 'order_id' string
    try:
        # Try as ObjectId
        obj_id_val = ObjectId(order_id) # Convert the route parameter
        order_doc = orders_col.find_one({"_id": obj_id_val})
    except InvalidId:
        # If not a valid ObjectId hex string, try as an integer
        try:
            int_id_val = int(order_id)
            order_doc = orders_col.find_one({"_id": int_id_val})
        except ValueError:
            # If not an integer, try as a direct string match
            order_doc = orders_col.find_one({"_id": order_id}) # Use the original string
    
    if not order_doc:
        return "Order not found", 404

    # Now, fetch the customer robustly using data from order_doc
    customer_doc = None
    customer_ref = order_doc.get('customer_id')  # New field, likely ObjectId
    legacy_customer_ref = order_doc.get('customerId') # Old field, likely int

    if customer_ref: # Primary reference field
        if isinstance(customer_ref, ObjectId):
            customer_doc = customers_col.find_one({"_id": customer_ref})
        else: # customer_ref is not an ObjectId, could be string representation of ObjectId, int, or other string
            try:
                # Try converting to ObjectId (if it's a string representation)
                customer_doc = customers_col.find_one({"_id": ObjectId(str(customer_ref))})
            except InvalidId:
                # Try as int (could be CustomerID or an _id if customer _ids are ints)
                try:
                    cust_int_id = int(str(customer_ref))
                    customer_doc = customers_col.find_one({"CustomerID": cust_int_id})
                    if not customer_doc: # If not found by CustomerID, try as _id
                        customer_doc = customers_col.find_one({"_id": cust_int_id})
                except ValueError: 
                    # Try as a plain string _id (if customer_ref was a string not convertible to ObjectId or int)
                    customer_doc = customers_col.find_one({"_id": str(customer_ref)})
    elif legacy_customer_ref is not None: # Fallback to legacy reference field
        try:
            cust_int_id = int(legacy_customer_ref) # Legacy is expected to be int for CustomerID
            customer_doc = customers_col.find_one({"CustomerID": cust_int_id})
        except (ValueError, TypeError):
            print(f"Warning: Could not parse legacy customerId '{legacy_customer_ref}' as int for order {order_id}")

    if not customer_doc:
        print(f"Warning: Customer not found for order {order_id}. Customer refs: main='{customer_ref}', legacy='{legacy_customer_ref}'")

    # Calculate total_value safely, defaulting to 0 if price or quantity is missing or not a number
    total_value = 0
    for item in order_doc.get('items', []):
        price = item.get('price', 0)
        quantity = item.get('quantity', 0)
        # Ensure price and quantity are numbers before multiplying
        if isinstance(price, (int, float)) and isinstance(quantity, (int, float)):
            total_value += price * quantity
        else:
            print(f"Warning: Invalid price or quantity for item in order {order_id}. Item: {item}")

    # Pass order_doc as 'order' and customer_doc as 'customer' to the template
    return render_template('order_details.html', 
                           order=order_doc, 
                           items=order_doc.get('items', []), 
                           total=total_value, 
                           customer=customer_doc)

@app.route('/cancel_order/<order_id>')
def cancel_order(order_id):
    try:
        order_obj_id = ObjectId(order_id)
    except InvalidId:
        # Handle invalid order_id string if necessary, e.g., flash a message or return an error page
        return "Invalid Order ID format", 400

    order = orders_col.find_one({"_id": order_obj_id})

    if order and order.get('status') != 'Cancelled': # Proceed only if order exists and is not already cancelled
        # Update order status
        orders_col.update_one({"_id": order_obj_id}, {"$set": {"status": "Cancelled"}})

        # Restore stock for items in the cancelled order
        if 'items' in order:
            for item in order['items']:
                product_id = item.get('product_id')
                quantity = item.get('quantity')
                
                if product_id and isinstance(quantity, int) and quantity > 0:
                    try:
                        # Ensure product_id is ObjectId if it's stored as such in items
                        if not isinstance(product_id, ObjectId):
                            product_id = ObjectId(product_id)
                        
                        products_col.update_one(
                            {"_id": product_id},
                            {"$inc": {"stock": quantity}} # Increment stock
                        )
                    except InvalidId:
                        print(f"Warning: Invalid product_id format ('{item.get('product_id')}') in order {order_id} during cancellation.")
                    except Exception as e:
                        print(f"Error updating stock for product {product_id} during order cancellation: {e}")
    
    return redirect(request.referrer or url_for('index'))

@app.route('/customer_summary')
def customer_summary():
    summary = list(customers_col.aggregate([
        {
            "$lookup": {
                "from": "orders",
                "localField": "_id", # Assumes customers_col._id is ObjectId
                "foreignField": "customer_id", # Matches orders.customer_id (ObjectId)
                "as": "customer_orders_objid"
            }
        },
        {
            "$lookup": {
                "from": "orders",
                "localField": "CustomerID", # Assumes customers_col.CustomerID is int
                "foreignField": "customerId", # Matches orders.customerId (int)
                "as": "customer_orders_intid"
            }
        },
        {
            "$addFields": {
                "all_orders_for_customer": {
                    "$concatArrays": ["$customer_orders_objid", "$customer_orders_intid"]
                }
            }
        },
        {
            "$addFields": {
                "TotalOrders": {"$size": "$all_orders_for_customer"},
                "TotalSpent": {
                    "$sum": {
                        "$map": {
                            "input": "$all_orders_for_customer",
                            "as": "order",
                            "in": {"$sum": {"$map": {"input": "$$order.items", "as": "item", "in": {"$multiply": ["$$item.price", "$$item.quantity"]}}}}
                        }
                    }
                }
            }
        },
        {
            "$project": {
                "CustomerID": 1,
                "Name": 1,
                "TotalOrders": 1,
                "TotalSpent": 1,
                "_id": 1 # Ensure _id is projected if needed by template or other logic
            }
        }
    ]))

    # Calculate total orders
    total_orders_val = orders_col.count_documents({})

    # Calculate total revenue
    total_revenue_val = 0
    revenue_agg_result = list(orders_col.aggregate([
        {"$match": {"items": {"$ne": None, "$not": {"$size": 0}}}}, # Only orders with items
        {"$unwind": "$items"},
        {"$group": {
            "_id": None,
            "total_revenue": {
                "$sum": {
                    "$multiply": [
                        {"$ifNull": ["$items.price", 0]},
                        {"$ifNull": ["$items.quantity", 0]}
                    ]
                }
            }
        }}
    ]))
    if revenue_agg_result and 'total_revenue' in revenue_agg_result[0]:
        total_revenue_val = revenue_agg_result[0]['total_revenue']

    # Calculate total unique customers who have placed orders
    customer_count_agg = list(orders_col.aggregate([
        {
            "$project": {
                "customerRefForCount": {
                    "$cond": {
                        "if": {"$ifNull": ["$customer_id", False]}, # Check if customer_id (ObjectId) exists
                        "then": {"$toString": "$customer_id"},
                        "else": { # Fallback to customerId (int)
                            "$cond": {
                                "if": {"$ifNull": ["$customerId", False]},
                                "then": {"$toString": "$customerId"}, # Convert int to string
                                "else": None # If neither exists
                            }
                        }
                    }
                }
            }
        },
        {"$match": {"customerRefForCount": {"$ne": None}}}, # Exclude orders with no customer ref
        {"$group": {"_id": "$customerRefForCount"}}, # Group by the unique stringified customer reference
        {"$count": "uniqueCustomers"}
    ]))
    total_customers_val = 0
    if customer_count_agg and 'uniqueCustomers' in customer_count_agg[0]:
        total_customers_val = customer_count_agg[0]['uniqueCustomers']
    
    return render_template('customer_summary.html',
                           summary=summary,
                           total_customers=total_customers_val,
                           total_orders=total_orders_val,
                           total_revenue=total_revenue_val)

@app.route('/add_customer', methods=['POST'])
def add_customer():
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone', '')

    if not name or not email:
        return jsonify({'success': False, 'message': 'Name and email are required'})

    if customers_col.find_one({"Email": email}):
        return jsonify({'success': False, 'message': 'Customer with this email already exists'})

    # Get the next CustomerID
    last_customer = customers_col.find_one({}, sort=[("CustomerID", -1)])
    next_customer_id = (last_customer['CustomerID'] + 1) if last_customer else 1

    result = customers_col.insert_one({
        "CustomerID": next_customer_id,
        "Name": name, 
        "Email": email, 
        "Phone": phone
    })
    # Keep JSON response consistent if client expects customer_id (ObjectId string) and customer_name
    return jsonify({'success': True, 'customer_id': str(result.inserted_id), 'customer_name': name})

@app.route('/add_product', methods=['POST'])
def add_product():
    name = request.form.get('name')
    price = request.form.get('price')
    stock = request.form.get('stock')

    if not name or not price or not stock:
        return jsonify({'success': False, 'message': 'All fields are required'})

    try:
        price = float(price)
        stock = int(stock)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid price or stock value'})

    # Use product_name to align with database and other template usage
    if products_col.find_one({"product_name": name}):
        return jsonify({'success': False, 'message': 'Product with this name already exists'})

    result = products_col.insert_one({"product_name": name, "price": price, "stock": stock})
    # Return product_name in JSON to be consistent with database field name
    return jsonify({'success': True, 'product_id': str(result.inserted_id), 'product_name': name})

@app.route('/delete_product', methods=['POST'])
def delete_product():
    data = request.get_json()
    product_id = data.get('product_id')

    if not product_id:
        return jsonify({'success': False, 'message': 'Product ID is required'})

    if orders_col.find_one({"items.product_id": ObjectId(product_id)}):
        return jsonify({'success': False, 'message': 'Cannot delete product that has been ordered'})

    result = products_col.delete_one({"_id": ObjectId(product_id)})

    if result.deleted_count == 0:
        return jsonify({'success': False, 'message': 'Product not found or already deleted'})

    return jsonify({'success': True, 'message': 'Product deleted successfully'})

@app.route('/update_stock', methods=['POST'])
def update_stock():
    data = request.get_json()
    product_id = data.get('product_id')
    new_stock = data.get('new_stock')

    if not product_id or new_stock is None:
        return jsonify({'success': False, 'message': 'Product ID and new stock are required'})

    try:
        new_stock = int(new_stock)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid stock value'})

    result = products_col.update_one({"_id": ObjectId(product_id)}, {"$set": {"stock": new_stock}})

    if result.modified_count == 0:
        return jsonify({'success': False, 'message': 'Product not found or stock unchanged'})

    return jsonify({'success': True, 'message': 'Stock updated successfully', 'new_stock': new_stock})

if __name__ == '__main__':
    app.run(debug=True)
