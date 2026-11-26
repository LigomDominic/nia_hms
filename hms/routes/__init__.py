def register_blueprints(app):
    from . import (admin, anc, auth, cashier, cleaner, consumables, doctor, expenses, fluid_balance, lab, main, nurse,
                   patients, payroll, pharmacy, requisitions, store, treatment)

    for module in (main, auth, patients, cashier, doctor, nurse, anc, lab, pharmacy, store, admin, cleaner, treatment,
                   consumables, fluid_balance, requisitions, expenses, payroll):
        app.register_blueprint(module.bp)
