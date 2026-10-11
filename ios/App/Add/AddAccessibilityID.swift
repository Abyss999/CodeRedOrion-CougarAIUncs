import Foundation

extension AccessibilityID {
    enum AddText {
        static let screen = "addtext"
        static let back = "addtext.back"
        static let title = "addtext.title"
        static let field = "addtext.field"
        static let mic = "addtext.mic"
        static let status = "addtext.status"
        static let find = "addtext.find"
        static let edit = "addtext.edit"
        static let results = "addtext.results"
        static let rows = "addtext.rows"          // row ids are addtext.rows.row.<i>
        static let empty = "addtext.empty"
        static let error = "addtext.error"
        static let notice = "addtext.notice"
        static let confirm = "addtext.confirm"
        static let confirmError = "addtext.confirm.error"
        static let parsing = "addtext.parsing"
    }

    enum Barcode {
        static let screen = "barcode"
        static let back = "barcode.back"
        static let scanner = "barcode.scanner"
        static let manualField = "barcode.manual.field"
        static let manualLookup = "barcode.manual.lookup"
        static func sample(_ code: String) -> String { "barcode.manual.sample.\(code)" }
        static let looking = "barcode.looking"
        static let result = "barcode.result"
        static let name = "barcode.result.name"
        static let source = "barcode.result.source"
        static let less = "barcode.result.less"
        static let more = "barcode.result.more"
        static let amount = "barcode.result.amount"
        static let add = "barcode.result.add"
        static let addError = "barcode.result.add.error"
        static let typeInstead = "barcode.typeinstead"
        static let notFound = "barcode.notfound"
        static let unreachable = "barcode.unreachable"
        static let retry = "barcode.retry"
        static let scanAgain = "barcode.scanagain"
    }

    enum Receipt {
        static let screen = "receipt"
        static let back = "receipt.back"
        static let scan = "receipt.scan"
        static let library = "receipt.library"
        static let analyzing = "receipt.analyzing"
        static let error = "receipt.error"
        static let unavailable = "receipt.unavailable"
        static let typeInstead = "receipt.typeinstead"
        static let empty = "receipt.empty"
        static let title = "receipt.title"
        static let total = "receipt.total"
        static let rows = "receipt.rows"          // row ids are receipt.rows.row.<i>
        static let confirm = "receipt.confirm"
        static let confirmError = "receipt.confirm.error"
    }
}
