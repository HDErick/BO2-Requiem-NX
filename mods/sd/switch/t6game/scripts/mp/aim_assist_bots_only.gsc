// Aim assist only against bots (pairs with patch_mp_aimassist.py)
// BO2 Requiem NX: /switch/t6game/scripts/mp/aim_assist_bots_only.gsc
//
// The patched t6mp.nro only enables the ADS auto-aim in multiplayer while this console
// runs the server and the dvar nx_aimassist_allowed is nonzero. This script runs on the
// host and keeps that dvar at 1 while every other player is a bot or plays on the host's
// console (split screen), and at 0 as soon as a remote human is in the match. It is
// checked once per second. When you join someone else's match the patch sees that this
// console is not the server and keeps auto-aim off, whatever the dvar says.

main()
{
    setdvar( "nx_aimassist_allowed", "0" );
    level thread aim_assist_allowed_watch();
}

aim_assist_allowed_watch()
{
    current = "";

    for (;;)
    {
        allowed = aim_assist_only_bots_and_local() ? "1" : "0";

        if ( allowed != current )
        {
            setdvar( "nx_aimassist_allowed", allowed );
            current = allowed;
        }

        wait 1;
    }
}

aim_assist_only_bots_and_local()
{
    if ( !isdefined( level.players ) )
        return false;

    foreach ( player in level.players )
    {
        if ( !player istestclient() && !player islocaltohost() )
            return false;
    }

    return true;
}
