import os
from flask import Flask, render_template, request, redirect, url_for, Response
from models import db, Expense
from sqlalchemy import func, case
from datetime import datetime, date
import csv

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.getcwd(), 'data', 'expense.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)    

@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    total_income = db.session.query(func.sum(Expense.amount))\
        .filter(Expense.type == 'income').scalar() or 0

    total_expense = db.session.query(func.sum(Expense.amount))\
        .filter(Expense.type == 'expense').scalar() or 0

    balance = total_income - total_expense

    today_expense = db.session.query(func.sum(Expense.amount))\
        .filter(Expense.type == 'expense', Expense.date == date.today())\
        .scalar() or 0

    recent = Expense.query.order_by(Expense.created_at.desc()).limit(5).all()

    # 🔹 SAFE DEFAULTS
    categories = []
    category_amounts = []
    dates = []
    daily_amounts = []

    category_data = db.session.query(
        Expense.category,
        func.sum(Expense.amount)
    ).filter(Expense.type == 'expense')\
     .group_by(Expense.category).all()

    if category_data:
        categories = [c[0] for c in category_data]
        category_amounts = [float(c[1]) for c in category_data]

    daily_data = db.session.query(
        Expense.date,
        func.sum(Expense.amount)
    ).filter(Expense.type == 'expense')\
     .group_by(Expense.date)\
     .order_by(Expense.date).all()

    if daily_data:
        dates = [d[0].strftime('%Y-%m-%d') for d in daily_data]
        daily_amounts = [float(d[1]) for d in daily_data]

    # Monthly income data
    monthly_income_data = db.session.query(
        func.strftime('%Y-%m', Expense.date).label('month'),
        func.sum(Expense.amount).label('total')
    ).filter(Expense.type == 'income')\
     .group_by(func.strftime('%Y-%m', Expense.date))\
     .order_by(func.strftime('%Y-%m', Expense.date)).all()

    monthly_income_labels = [m.month for m in monthly_income_data]
    monthly_income_amounts = [float(m.total) for m in monthly_income_data]

    return render_template(
        'dashboard.html',
        total_income=total_income,
        total_expense=total_expense,
        balance=balance,
        today_expense=today_expense,
        recent=recent,
        categories=categories,
        category_amounts=category_amounts,
        dates=dates,
        daily_amounts=daily_amounts,
        monthly_income_labels=monthly_income_labels,
        monthly_income_amounts=monthly_income_amounts
    )

@app.route('/report', methods=['GET'])
def report():
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')

    # ================= DEFAULT VALUES =================
    summary = []
    categories = []
    amounts = []

    total_expense = 0
    avg_daily_expense = 0
    max_expense = 0
    total_transactions = 0

    top_category = None
    top_category_amount = 0
    top_category_percent = 0

    total_income = 0
    total_expense_ie = 0

    payment_labels = []
    payment_amounts = []

    monthly_summary = []

    # ================= FILTERED LOGIC =================
    if from_date and to_date:
        from_d = datetime.strptime(from_date, "%Y-%m-%d")
        to_d = datetime.strptime(to_date, "%Y-%m-%d")

        # ---------- KPIs ----------
        total_expense = db.session.query(func.sum(Expense.amount))\
            .filter(Expense.type == 'expense',
                    Expense.date.between(from_d, to_d))\
            .scalar() or 0

        max_expense = db.session.query(func.max(Expense.amount))\
            .filter(Expense.type == 'expense',
                    Expense.date.between(from_d, to_d))\
            .scalar() or 0

        total_transactions = Expense.query.filter(
            Expense.type == 'expense',
            Expense.date.between(from_d, to_d)
        ).count()

        days = (to_d - from_d).days + 1
        avg_daily_expense = round(total_expense / days, 2) if days > 0 else 0

        # ---------- CATEGORY SUMMARY ----------
        result = db.session.query(
            Expense.category,
            func.sum(Expense.amount).label('total')
        ).filter(
            Expense.type == 'expense',
            Expense.date.between(from_d, to_d)
        ).group_by(Expense.category).all()

        summary = result
        categories = [r.category for r in result]
        amounts = [float(r.total) for r in result]

        # ---------- TOP SPENDING CATEGORY ----------
        top_result = db.session.query(
            Expense.category,
            func.sum(Expense.amount).label('total')
        ).filter(
            Expense.type == 'expense',
            Expense.date.between(from_d, to_d)
        ).group_by(Expense.category)\
         .order_by(func.sum(Expense.amount).desc())\
         .first()

        if top_result and total_expense > 0:
            top_category = top_result.category
            top_category_amount = float(top_result.total)
            top_category_percent = round(
                (top_category_amount / total_expense) * 100, 2
            )

        # ---------- INCOME vs EXPENSE ----------
        total_income = db.session.query(func.sum(Expense.amount))\
            .filter(Expense.type == 'income',
                    Expense.date.between(from_d, to_d))\
            .scalar() or 0

        total_expense_ie = total_expense

        # ---------- PAYMENT MODE ANALYSIS ----------
        payment_data = db.session.query(
            Expense.payment_mode,
            func.sum(Expense.amount)
        ).filter(
            Expense.type == 'expense',
            Expense.date.between(from_d, to_d)
        ).group_by(Expense.payment_mode).all()

        payment_labels = [p[0] for p in payment_data]
        payment_amounts = [float(p[1]) for p in payment_data]

        # ---------- MONTHLY SUMMARY ----------
        monthly_data = db.session.query(
            func.strftime('%Y-%m', Expense.date).label('month'),

            func.sum(
                case(
                    (Expense.type == 'income', Expense.amount),
                    else_=0
                )
            ).label('income'),

            func.sum(
                case(
                    (Expense.type == 'expense', Expense.amount),
                    else_=0
                )
            ).label('expense')

        ).filter(
            Expense.date.between(from_d, to_d)
        ).group_by('month').all()


        for m in monthly_data:
            monthly_summary.append({
                'month': m.month,
                'income': float(m.income),
                'expense': float(m.expense),
                'balance': float(m.income - m.expense)
            })

    return render_template(
        'report.html',
        summary=summary,
        categories=categories,
        amounts=amounts,
        total_expense=total_expense,
        avg_daily_expense=avg_daily_expense,
        max_expense=max_expense,
        total_transactions=total_transactions,
        top_category=top_category,
        top_category_amount=top_category_amount,
        top_category_percent=top_category_percent,
        total_income=total_income,
        total_expense_ie=total_expense_ie,
        payment_labels=payment_labels,
        payment_amounts=payment_amounts,
        monthly_summary=monthly_summary
    )


@app.route('/add', methods=['GET', 'POST'])
def add_transaction():
    if request.method == 'POST':
        expense = Expense(
            description=request.form.get('description'),
            amount=float(request.form['amount']),
            date=datetime.strptime(request.form['date'], '%Y-%m-%d'),
            category=request.form['category'],
            payment_mode=request.form['payment_mode'],
            type=request.form['type']
        )
        db.session.add(expense)
        db.session.commit()
        return redirect(url_for('transactions'))

    return render_template('add_transaction.html')


@app.route('/transactions')
def transactions():
    query = Expense.query

    # Apply filters
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    category = request.args.get('category')
    payment_mode = request.args.get('payment_mode')
    type_filter = request.args.get('type')

    if from_date:
        query = query.filter(Expense.date >= datetime.strptime(from_date, '%Y-%m-%d').date())
    if to_date:
        query = query.filter(Expense.date <= datetime.strptime(to_date, '%Y-%m-%d').date())
    if category:
        query = query.filter(Expense.category == category)
    if payment_mode:
        query = query.filter(Expense.payment_mode == payment_mode)
    if type_filter:
        query = query.filter(Expense.type == type_filter)

    expenses = query.order_by(Expense.date.desc()).all()
    return render_template('transactions.html', expenses=expenses)


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_expense(id):
    expense = Expense.query.get_or_404(id)

    if request.method == 'POST':
        expense.description = request.form.get('description')
        expense.amount = float(request.form['amount'])
        expense.date = datetime.strptime(request.form['date'], '%Y-%m-%d')
        expense.category = request.form['category']
        expense.payment_mode = request.form['payment_mode']
        expense.type = request.form['type']

        db.session.commit()
        return redirect(url_for('transactions'))

    return render_template('edit_expense.html', expense=expense)

@app.route('/delete/<int:id>')
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    db.session.delete(expense)
    db.session.commit()
    return redirect(url_for('transactions'))

@app.route('/export')
def export_csv():
    expenses = Expense.query.order_by(Expense.date.desc()).all()

    def generate():
        data = []
        header = ['Date', 'Description', 'Category', 'Amount', 'Type', 'Payment Mode']
        data.append(header)

        for e in expenses:
            data.append([
                e.date,
                e.description,
                e.category,
                e.amount,
                e.type,
                e.payment_mode
            ])

        for row in data:
            yield ','.join([str(item) if item is not None else '' for item in row]) + '\n'

    return Response(
        generate(),
        mimetype='text/csv',
        headers={
            "Content-Disposition": "attachment; filename=expenses.csv"
        }
    )



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

