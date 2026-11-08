/// One line of "what the tutor is doing", from the agent loop's ``label`` field.
///
/// The state machine is deliberately three-valued: ``running`` until the tool reports,
/// then ``done`` or ``failed``. A chip that never settles would leave a learner
/// wondering whether the tutor is still working, and a chip that only ever shows
/// success would hide the refusals that are part of an honest turn.
struct ChatActivity: Identifiable, Equatable {
    enum State: String, Equatable { case running, done, failed }
    let id: String
    let label: String
    var state: State
}
