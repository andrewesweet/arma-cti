/*
 * Author: arma-cti
 * A Squad owns a vehicle it can walk to, and stops owning one it cannot.
 * Runs on the server.
 *
 * Interior to the server's own call graph, so it carries no locality guard: its
 * one caller is cti_fnc_transportWatch, which `missions/cti.Stratis/initServer.sqf`
 * starts on the server and nowhere else (#118, ADR-0041).
 *
 * ## Why this exists, which is a corpus run rather than a design instinct
 *
 * `cti_fnc_transportIssue` puts a Squad's vehicle in the group's own pool so the
 * engine boards it for a distant waypoint (ADR-0059, Ruling 4). The engine's
 * side of that bargain is documented for the Move waypoint —
 * "Groups will automatically board any transport vehicles they own if the next
 * waypoint is far enough away" (`topics/Waypoints.wiki`) — and
 * `topics/AI_Group_Vehicle_Management.wiki` adds, under a `{{Clarify}}` tag,
 * that "the distance from the vehicle may also play a role". What neither says
 * is what a group does when the vehicle it owns is *further away than where it
 * was sent*.
 *
 * The corpus answered it. `campaign-end`'s assaulting Squad is staged 250 m from
 * the enemy HQ while its truck stands at its own Base, 4.4 km behind it; at
 * `0b4fa85` the Squad walked about 980 m in the wrong direction and never came
 * a metre closer to the HQ than the point it was put down on
 * (`end_probe_campaign_never_ended ... range=1227.91 closest=250`, evidence
 * `~/.arma-cti/runs/20260805T071859Z-campaign-end`). A Squad marching kilometres
 * backwards to fetch a lorry is the opposite of the ruling this feature carries
 * out, and it is not something a Commander can see, price or countermand.
 *
 * So ownership is made local: a Squad owns its vehicle while it is standing by
 * it, and does not while it is not. Both halves are needed rather than only the
 * disowning one — a Squad that walks home to a truck it was disowned from has to
 * be given it back, or the second march is on foot for good.
 *
 * ## Why distance rather than Place
 *
 * `cti_fnc_placeOf` answers "" for the open ground between Places, so a Squad
 * marching between two towns and a truck abandoned in a third field would read
 * as being in the same nowhere. A Squad riding in its own truck is at distance
 * nought from it, which is the case that has to keep working, and a metre count
 * is the only reading that gets both right.
 *
 * ## What the crew guard is for
 *
 * `commands/leaveVehicle.wiki` says the command unassigns every crew member from
 * its role, and its own note records that "AI crew however will also disembark".
 * Disowning a truck with men in it would therefore put them out of it, possibly
 * at speed. A truck with nobody in it cannot eject anybody, so the far branch is
 * taken only for an empty one — and a crewed truck more than 150 m from its
 * leader is a Squad half-mounted, which the next sweep will find settled.
 *
 * Arguments:
 * 0: the Squad's group <GROUP>
 * 1: the Squad id <STRING>
 *
 * Return Value: <BOOL> whether the pool was changed
 */

params [["_group", grpNull, [grpNull]], ["_squadId", "", [""]]];

// How close a Squad has to be to its vehicle to own it. The Base radius
// cti_fnc_placeRadius stands in for a Place with no authored one — this project's
// one answer to "how close counts as being at one Place" — so a Squad and its
// truck inside it are at the same place by the only definition we have. Well
// beyond a group's formation spread, and far short of any march.
#define NEAR_METRES 150

private _held = _group getVariable ["cti_transport", objNull];
// Nothing to pool, or a group this machine may not write to: `addVehicle` and
// `leaveVehicle` are both `arg= local` (vendored wiki), and an AI group with a
// player leader is local to that player's machine. A player squad leader drives
// his own truck and needs neither call — ADR-0059, Ruling 4.
if (isNull _held || {!alive _held} || {!local _group}) exitWith { false };

private _near = _held distance leader _group <= NEAR_METRES;
private _pooled = _held in assignedVehicles _group;

if (_near && !_pooled) exitWith {
    _group addVehicle _held;
    diag_log format ["CTI|transport_pooled squad=%1 metres=%2",
        _squadId, round (_held distance leader _group)];
    true
};

if (!_near && _pooled && {crew _held isEqualTo []}) exitWith {
    _group leaveVehicle _held;
    diag_log format ["CTI|transport_disowned squad=%1 metres=%2",
        _squadId, round (_held distance leader _group)];
    true
};

false
