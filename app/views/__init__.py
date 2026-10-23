"""Satu Blueprint per modul."""


def register_blueprints(app):
    from . import (approval, auth, gr, main, master, ocr, po, pr, report, rfq, users,
                   vendor_portal)
    for module in (auth, main, users, master, pr, approval, rfq, vendor_portal, po, gr, report, ocr):
        app.register_blueprint(module.bp)
