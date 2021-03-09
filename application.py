import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    symbols = db.execute("SELECT ALL symbol FROM stocks WHERE users_id = ?", session["user_id"])
    for symbol in symbols:
        price = lookup(symbol["symbol"])['price']
        db.execute("UPDATE stocks SET price = ? WHERE symbol = ? AND users_id = ?", price, symbol['symbol'], session["user_id"])
        share = db.execute("SELECT shares FROM stocks WHERE symbol = ? AND users_id = ?", symbol['symbol'], session["user_id"])[0]
        shares = share['shares']
        total = float("%0.2f" % float(shares * price))
        db.execute("UPDATE stocks SET total = ? WHERE symbol = ?",total ,symbol['symbol'])
    stocks = db.execute("SELECT * FROM stocks JOIN users ON stocks.users_id = users.id WHERE users_id = ? ORDER BY symbol", session["user_id"])
    cash_r = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]
    cash = float(("%0.2f" % float(cash_r['cash'])))
    s = db.execute("SELECT SUM(total) FROM stocks WHERE users_id = ?", session["user_id"])[0]
    su = s['SUM(total)']
    if not su:
        su = 0
        value = float(("%0.2f" % float(cash_r['cash'])))
    else:
        su = s['SUM(total)']
        value = "%0.2f" % float(su + cash)

    return render_template("index.html", stocks = stocks, cash = cash, value = value)




@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        if not request.form.get("symbol"):
            return apology("Please, provide stock symbol", 403)
        elif lookup(request.form.get("symbol")) == None:
            return apology("Incorrect stock symbol", 403)
        elif not request.form.get("number") or int(request.form.get("number")) < 1:
            return apology("Incorrect number of stocks", 403)
        else:
            price = lookup(request.form.get("symbol"))['price'] * float(request.form.get("number"))
            cash = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])[0]
            available = float("%0.2f" % (cash['cash']))

            if (available - price) < 0:
                return apology("Sorry, you dont't have enough money", 403)
            else:
                stockname = lookup(request.form.get("symbol"))['name']
                checks = (db.execute("SELECT name FROM stocks WHERE users_id = ?", session["user_id"]))
                if not checks:
                    db.execute("INSERT INTO stocks(users_id, symbol, name, shares, price, total) VALUES(?, ?, ?, ?, ?, ?)",session["user_id"], request.form.get("symbol"),stockname, float(request.form.get("number")), lookup(request.form.get("symbol"))['price'], price)
                    db.execute("UPDATE users SET cash = ? WHERE id = ?", (available-price) ,session["user_id"])
                    db.execute("INSERT INTO history(symbol, shares, price, time, id) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)", request.form.get("symbol"), request.form.get("number"), lookup(request.form.get("symbol"))['price'], session["user_id"])
                    return redirect("/")
                else:
                    for check in checks:
                        if check['name'] == stockname:
                            stocks = list(db.execute("SELECT * FROM stocks WHERE users_id = ? AND name = ?", session["user_id"], stockname))
                            stock = stocks[0]
                            shares = float(stock['shares']) + float(request.form.get("number"))
                            price_s = lookup(request.form.get("symbol"))['price']
                            total = float("%0.2f" % (float(price_s) * float(shares)))
                            db.execute("UPDATE stocks SET shares = ?, total = ? , price = ? WHERE name = ? AND users_id = ?", shares, total, price_s, stockname, session["user_id"])
                            db.execute("UPDATE users SET cash = ? WHERE id = ?", (available-price) ,session["user_id"])
                            db.execute("INSERT INTO history(symbol, shares, price, time, id) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)", request.form.get("symbol"), request.form.get("number"), price_s, session["user_id"])
                            return redirect("/")
                        else:
                            continue

                    db.execute("INSERT INTO stocks(users_id, symbol, name, shares, price, total) VALUES(?, ?, ?, ?, ?, ?)",session["user_id"], request.form.get("symbol"),stockname, float(request.form.get("number")), lookup(request.form.get("symbol"))['price'], price)
                    db.execute("UPDATE users SET cash = ? WHERE id = ?", (available-price) ,session["user_id"])
                    db.execute("INSERT INTO history(symbol, shares, price, time, id) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)", request.form.get("symbol"), request.form.get("number"), lookup(request.form.get("symbol"))['price'], session["user_id"])
                    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM history WHERE id = ?", session["user_id"])
    if not history:
        return apology("No transactions have been made yet", 403)
    return render_template("history.html", history = history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        if lookup(request.form.get("symbol")) == None:
            return apology("Wrong stock symbol", 403)
        else:
            back = lookup(request.form.get("symbol"))
            return render_template("quoted.html", message = f"Price for one share of {back['name']} ({back['symbol']}) is {back['price']}")


@app.route("/change", methods=["GET", "POST"])
@login_required
def change():
    if request.method == "GET":
        return render_template("change.html")
    else:
        if not request.form.get("old"):
            return apology("Please, provide old password", 403)
        elif not request.form.get("password"):
            return apology("Provide new password", 403)
        elif not request.form.get("password_2"):
            return apology("Confirm new password", 403)
        elif request.form.get("password") != request.form.get("password_2"):
            return apology("Passwords don't match", 403)

        rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        if not check_password_hash(rows[0]["hash"], request.form.get("old")):
            return apology("Old password incorrect", 403)
        if not check_password_hash(rows[0]["hash"], request.form.get("password")):
            db.execute("UPDATE users SET hash = ? WHERE id = ?", generate_password_hash(request.form.get("password")), session["user_id"])
            return redirect("/logout")
        return apology("New password is same as old one", 403)

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        if not request.form.get("username"):
            return apology("must provide username", 403)
        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)
        elif (request.form.get("password") != request.form.get("password_2")):
            return apology("passwords don't match", 403)

        rows = db.execute("SELECT * FROM users WHERE username = :username",
                    username=request.form.get("username"))

        # Ensure username doen't exists
        if len(rows) == 1:
            return apology("This username already exists", 403)
        else:
            db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", request.form.get("username"), generate_password_hash(request.form.get("password")))
            return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        symbol = db.execute("SELECT symbol FROM stocks WHERE users_id = ?", session["user_id"])
        if not symbol:
            return apology("No stocks for sell", 403)
        else:
            symbols = symbol
            return render_template("sell.html", symbols = symbols)

    else:
        if not request.form.get("shares") or not request.form.get("symbol"):
            return apology("Complete all fields first", 403)
        share = db.execute("SELECT shares FROM stocks WHERE symbol = ? AND users_id = ?", request.form.get("symbol"), session["user_id"])[0]
        shares = float(share['shares'])
        try:
            sell_n = int(request.form.get("shares"))
        except ValueError:
            return apology("Enter a valid number of shares you want to sell", 403)
        if sell_n < 0:
            return apology("Input valid number of shares, please")
        if sell_n > shares:
            return apology("Not enough shares, try smaller number", 403)
        share_new = shares - sell_n
        price_now = lookup(request.form.get("symbol"))['price']
        value = sell_n * price_now
        cashs = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]
        cash = float("%0.2f" % cashs['cash'])
        cash_new = float("%0.2f" % (cash + value))
        total_new = float("%0.2f" % (share_new * price_now))
        db.execute("UPDATE stocks SET shares = ?, price = ?, total = ? WHERE symbol = ? AND users_id = ?", share_new, price_now, total_new, request.form.get("symbol"), session["user_id"])
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash_new, session["user_id"])
        db.execute("INSERT INTO history(symbol, shares, price, time, id) VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)", request.form.get("symbol"), -(sell_n), price_now, session["user_id"])
        if share_new == 0:
            db.execute("DELETE FROM stocks WHERE symbol = ? AND users_id = ?", request.form.get("symbol"), session["user_id"])

        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
