
import os
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "patel-rental-change-this-secret"
)

database_url = os.environ.get("DATABASE_URL", "sqlite:///patel_rental.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# DATABASE MODELS

class Generator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    kva = db.Column(db.String(30))
    serial = db.Column(db.String(100))
    status = db.Column(db.String(30), default="Available")
    notes = db.Column(db.Text)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    company = db.Column(db.String(100))
    address = db.Column(db.Text)


class Rental(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    generator_id = db.Column(db.Integer, db.ForeignKey("generator.id"))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    rate_type = db.Column(db.String(20), default="Daily")
    rate = db.Column(db.Float, default=0)
    advance = db.Column(db.Float, default=0)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default="Active")

    customer = db.relationship("Customer")
    generator = db.relationship("Generator")


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rental_id = db.Column(db.Integer, db.ForeignKey("rental.id"))
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, default=date.today)
    note = db.Column(db.String(200))

    rental = db.relationship("Rental")


# LOGIN

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = os.environ.get("ADMIN_USER", "kk")
        password = os.environ.get("ADMIN_PASSWORD", "harshuu")

        if (request.form.get("username") == username and
                request.form.get("password") == password):
            session["logged_in"] = True
            return redirect(url_for("dashboard"))

        flash("Wrong username or password")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# DASHBOARD

@app.route("/")
@login_required
def dashboard():
    total_generators = Generator.query.count()
    available = Generator.query.filter_by(status="Available").count()
    active_rentals = Rental.query.filter_by(status="Active").count()
    total_customers = Customer.query.count()

    total_payments = db.session.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).scalar()

    rentals = Rental.query.order_by(Rental.id.desc()).limit(5).all()

    return render_template(
        "dashboard.html",
        total_generators=total_generators,
        available=available,
        active_rentals=active_rentals,
        total_customers=total_customers,
        total_payments=total_payments,
        rentals=rentals
    )


# GENERATORS

@app.route("/generators", methods=["GET", "POST"])
@login_required
def generators():
    if request.method == "POST":
        item = Generator(
            name=request.form["name"],
            kva=request.form.get("kva"),
            serial=request.form.get("serial"),
            notes=request.form.get("notes")
        )
        db.session.add(item)
        db.session.commit()
        flash("Generator added successfully")
        return redirect(url_for("generators"))

    items = Generator.query.order_by(Generator.id.desc()).all()
    return render_template("generators.html", items=items)


@app.route("/generator/delete/<int:id>")
@login_required
def delete_generator(id):
    item = db.session.get(Generator, id)
    if item:
        if Rental.query.filter_by(generator_id=id, status="Active").first():
            flash("Generator is currently rented")
        else:
            db.session.delete(item)
            db.session.commit()
            flash("Generator deleted")
    return redirect(url_for("generators"))


# CUSTOMERS

@app.route("/customers", methods=["GET", "POST"])
@login_required
def customers():
    if request.method == "POST":
        customer = Customer(
            name=request.form["name"],
            phone=request.form.get("phone"),
            company=request.form.get("company"),
            address=request.form.get("address")
        )
        db.session.add(customer)
        db.session.commit()
        flash("Customer added")
        return redirect(url_for("customers"))

    items = Customer.query.order_by(Customer.id.desc()).all()
    return render_template("customers.html", items=items)


# RENTALS

@app.route("/rentals", methods=["GET", "POST"])
@login_required
def rentals():
    if request.method == "POST":
        generator = db.session.get(
            Generator, int(request.form["generator_id"])
        )

        if not generator or generator.status != "Available":
            flash("Generator is not available")
            return redirect(url_for("rentals"))

        rental = Rental(
            customer_id=int(request.form["customer_id"]),
            generator_id=generator.id,
            start_date=datetime.strptime(
                request.form["start_date"], "%Y-%m-%d"
            ).date(),
            rate_type=request.form["rate_type"],
            rate=float(request.form["rate"]),
            advance=float(request.form.get("advance") or 0),
            notes=request.form.get("notes")
        )

        db.session.add(rental)
        generator.status = "Rented"

        db.session.flush()

        if rental.advance > 0:
            payment = Payment(
                rental_id=rental.id,
                amount=rental.advance,
                note="Advance payment"
            )
            db.session.add(payment)

        db.session.commit()
        flash("Rental started successfully")
        return redirect(url_for("rentals"))

    customers_list = Customer.query.all()
    generators_list = Generator.query.filter_by(status="Available").all()
    items = Rental.query.order_by(Rental.id.desc()).all()

    return render_template(
        "rentals.html",
        customers=customers_list,
        generators=generators_list,
        items=items
    )


@app.route("/rental/<int:id>")
@login_required
def rental_detail(id):
    rental = db.session.get(Rental, id)
    if not rental:
        return redirect(url_for("rentals"))

    payments = Payment.query.filter_by(rental_id=id).all()
    paid = sum(p.amount for p in payments)

    today = rental.end_date or date.today()
    days = max(1, (today - rental.start_date).days + 1)

    if rental.rate_type == "Monthly":
        units = (days + 29) // 30
    else:
        units = days

    total = units * rental.rate
    balance = total - paid

    return render_template(
        "rental_detail.html",
        rental=rental,
        payments=payments,
        paid=paid,
        days=days,
        total=total,
        balance=balance
    )


@app.route("/rental/<int:id>/payment", methods=["POST"])
@login_required
def add_payment(id):
    rental = db.session.get(Rental, id)
    if not rental or rental.status != "Active":
        flash("This rental is not active")
        return redirect(url_for("rentals"))

    amount = float(request.form.get("amount") or 0)

    if amount <= 0:
        flash("Enter a valid payment amount")
    else:
        payment = Payment(
            rental_id=id,
            amount=amount,
            note=request.form.get("note")
        )
        db.session.add(payment)
        db.session.commit()
        flash("Payment recorded")

    return redirect(url_for("rental_detail", id=id))


@app.route("/rental/<int:id>/return", methods=["POST"])
@login_required
def return_generator(id):
    rental = db.session.get(Rental, id)

    if rental and rental.status == "Active":
        rental.end_date = date.today()
        rental.status = "Returned"
        rental.generator.status = "Available"
        db.session.commit()
        flash("Generator returned successfully")

    return redirect(url_for("rental_detail", id=id))


# PAYMENTS

@app.route("/payments")
@login_required
def payments():
    items = Payment.query.order_by(Payment.id.desc()).all()
    total = sum(p.amount for p in items)
    return render_template("payments.html", items=items, total=total)


# REPORTS

@app.route("/reports")
@login_required
def reports():
    items = Rental.query.order_by(Rental.id.desc()).all()
    total = db.session.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).scalar()

    return render_template("reports.html", items=items, total=total)


@app.route("/health")
def health():
    return {"status": "ok"}


# CREATE DATABASE

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
