import SwiftUI

// Connect-area tokens (Connect, ConnectPending, GroupDetail, FriendScan, FriendAdded artboards).
// Declared here, additively, so the shared Theme.swift stays untouched.

extension Theme.Colors {
    /// QR modules: ink in light mode, and the same dark ink in dark mode, so a scanner always sees dark on light.
    static let qrInk = Color(light: 0x13261A, dark: 0x13261A)
    /// QR background: lime in both modes (lime does not change in dark mode).
    static let qrGround = Color(light: 0xD9EC8F, dark: 0xD9EC8F)
}

extension Theme.Size {
    /// Icon / initials circle in friend and group rows (artboards: 36 pt).
    static let rowIcon: CGFloat = 36
    /// Friend / group row minimum height (artboards: 52 pt).
    static let connectRow: CGFloat = 52
    /// Inline text field + button rows (artboards: 48 pt).
    static let connectControl: CGFloat = 48
    /// The QR on the My code card.
    static let qrCard: CGFloat = 96
    /// The QR on the GroupDetail invite code.
    static let qrLarge: CGFloat = 220
    /// Square scan window on FriendScan.
    static let scanWindow: CGFloat = 280
    /// Big avatar on FriendAdded.
    static let successAvatar: CGFloat = 96
}

extension Theme.Spacing {
    /// Extra room around the GroupDetail invite code (round 3/4: more breathing room).
    static let inviteGap: CGFloat = 40
}

extension AccessibilityID {
    enum Connect {
        static let screen = "connect"
        static let close = "connect.close"
        static let requests = "connect.requests"
        static func accept(_ id: String) -> String { "connect.accept.\(id)" }
        static func decline(_ id: String) -> String { "connect.decline.\(id)" }
        static func friend(_ id: String) -> String { "connect.friend.\(id)" }
        static func sent(_ id: String) -> String { "connect.sent.\(id)" }
        static func withdraw(_ id: String) -> String { "connect.withdraw.\(id)" }
        static let addFriendToggle = "connect.addFriend.toggle"
        static let addFriendField = "connect.addFriend.email"
        static let addFriendSend = "connect.addFriend.send"
        static let createGroup = "connect.group.create"
        static let createGroupField = "connect.group.create.name"
        static let createGroupSubmit = "connect.group.create.submit"
        static let joinGroup = "connect.group.join"
        static let joinGroupField = "connect.group.join.code"
        static let joinGroupSubmit = "connect.group.join.submit"
        static func group(_ id: String) -> String { "connect.group.\(id)" }
        static let myCode = "connect.mycode"
        static let myCodeQR = "connect.mycode.qr"
        static let myCodeTimer = "connect.mycode.timer"
        static let myCodeCopy = "connect.mycode.copy"
        static let scan = "connect.scan"
    }

    enum GroupDetailScreen {
        static let screen = "groupdetail"
        static let members = "groupdetail.members"
        static let inviteCode = "groupdetail.invite.code"
        static let showQR = "groupdetail.invite.showqr"
        static let qr = "groupdetail.invite.qr"
        static let share = "groupdetail.invite.share"
        static let leave = "groupdetail.leave"
        static let leaveConfirm = "groupdetail.leave.confirm"
    }

    enum FriendScan {
        static let screen = "friendscan"
        static let scanner = "friendscan.scanner"
        static let confirm = "friendscan.confirm"
        static let confirmAdd = "friendscan.confirm.add"
        static let confirmCancel = "friendscan.confirm.cancel"
        static let manualField = "friendscan.manual.field"
        static let manualAdd = "friendscan.manual.add"
        static let error = "friendscan.error"
    }

    enum FriendAdded {
        static let screen = "friendadded"
        static let message = "friendadded.message"
        static let done = "friendadded.done"
        static let scanAnother = "friendadded.scanAnother"
    }
}
