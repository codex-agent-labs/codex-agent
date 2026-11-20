import AuthenticationServices
import CodexAgent
import XCTest
@testable import CodexAgentAuthentication

@MainActor
final class CodexAuthorizationBrowserTests: XCTestCase {
    func testGenericBrowserOpensTypedExternalURLAndCancelsPresentation() throws {
        let store = BrowserStore()
        let browser = CodexWebAuthenticationBrowser(
            browserFactory: { _, completion in
                let session = FakeBrowserSession(completion: completion)
                store.sessions.append(session)
                return session
            },
            anchorProvider: { ASPresentationAnchor() }
        )

        let presentation = try browser.open(
            url: CodexAuthorizationUrl.companion.external(value: "https://example.com/oauth")
        )
        XCTAssertEqual(store.sessions.count, 1)
        presentation.close()
        XCTAssertEqual(store.sessions[0].cancellationCount, 1)
    }

    func testFailedBrowserSessionIsCancelled() throws {
        let session = FakeBrowserSession(completion: { _, _ in }, startResult: false)
        let browser = CodexWebAuthenticationBrowser(
            browserFactory: { _, _ in session },
            anchorProvider: { ASPresentationAnchor() }
        )

        let presentation = try browser.open(
            url: CodexAuthorizationUrl.companion.external(value: "https://example.com/oauth")
        )

        XCTAssertEqual(session.cancellationCount, 1)
        presentation.close()
        XCTAssertEqual(session.cancellationCount, 1)
    }

}

@MainActor
private final class BrowserStore {
    var sessions: [FakeBrowserSession] = []
}

@MainActor
private final class FakeBrowserSession: CodexBrowserSession {
    private let completion: (URL?, Error?) -> Void
    private let startResult: Bool
    private(set) var cancellationCount = 0

    init(completion: @escaping (URL?, Error?) -> Void, startResult: Bool = true) {
        self.completion = completion
        self.startResult = startResult
    }

    func start() -> Bool { startResult }

    func cancel() {
        cancellationCount += 1
    }
}
