"""Printers"""

import logging
import os
import subprocess
from odoo import api, fields, models
from odoo.tools.translate import _
from odoo.tools.misc import find_in_path
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def _find_lpr_exec():
    """Find usable lpr executable"""
    try:
        lpr_exec = find_in_path('lpr')
        return lpr_exec
    except IOError:
        raise UserError(_("Cannot find lpr executable"))


class Printer(models.Model):
    """Printer"""

    _name = 'print.printer'
    _description = 'Printer'

    name = fields.Char(string="Name", index=True, required=True)
    barcode = fields.Char(string="Barcode", index=True)
    queue = fields.Char(string="Print Queue Name", index=True)
    is_default = fields.Boolean(string="System Default", index=True,
                                default=False)

    _sql_constraints = [('barcode_uniq', 'unique (barcode)',
                         "The Barcode must be unique"),
                        ('single_default',
                         'exclude (is_default with =) where (is_default)',
                         "There must be only one System Default Printer")]

    def _printers(self):
        """Determine printers to use"""

        # Use explicitly specified list of printers, falling back to
        # user's default printer, falling back to system default
        # printer
        printers = (self or self.env.user.printer_id or
                    self.search([('is_default', '=', True)]))
        if not printers:
            raise UserError(_("No default printer specified"))
        return printers

    def _spool_lpr(self, document, title=None, copies=1):
        """Spool document to printer via lpr"""
        lpr_exec = _find_lpr_exec()
        for printer in self._printers():

            # Construct lpr command line
            args = [lpr_exec]
            if printer.queue:
                args += ['-P', printer.queue]
            if title is not None:
                args += ['-T', title]
            if copies > 1:
                args += ['-#', str(copies)]

            # Pipe document into lpr
            _logger.info("Printing via %s", ' '.join(args))
            lpr = subprocess.Popen(args, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
            output = lpr.communicate(document)[0]
            if lpr.returncode != 0:
                raise UserError(_("lpr failed (error code: %s). Message: %s") %
                                (str(lpr.returncode), output))

    @api.multi
    def spool(self, document, title=None, copies=1):
        """Spool document to printer"""

        # Spool document via OS-dependent spooler mechanism
        if os.name == 'posix':
            self._spool_lpr(document, title=title, copies=copies)
        else:
            raise UserError(_("Cannot print on OS: %s" % os.name))
        return True

    @api.multi
    def spool_report(self, docids, report_name, data=None, title=None,
                     copies=1):
        """Spool report to printer"""
        # pylint: disable=too-many-arguments

        # Generate report
        if isinstance(report_name, models.BaseModel):
            report = report_name
        else:
            name = report_name
            Report = self.env['ir.actions.report']
            report = Report._get_report_from_name(name)
            if not report:
                report = self.env.ref(name, raise_if_not_found=False)
            if not report:
                raise UserError(_("Undefined report %s") % name)
        document = report.render(docids, data)[0]

        # Use report name and document IDs as title if no title specified
        if title is None:
            title = ("%s %s" % (report.name, str(docids)))

        # Spool generated report to printer(s)
        self.spool(document, title=title, copies=copies)
        return True

    @api.multi
    def spool_test_page(self):
        """Print test page"""
        for printer in self._printers():
            printer.spool_report(printer.ids, 'print.report_test_page',
                                 title="Test page")
        return True

    @api.multi
    def set_user_default(self):
        """Set as user default printer"""
        self.ensure_one()
        self.env.user.printer_id = self
        return True

    @api.multi
    def set_system_default(self):
        """Set as system default printer"""
        self.ensure_one()
        self.search([('is_default', '=', True)]).write({'is_default': False})
        self.is_default = True
        return True
