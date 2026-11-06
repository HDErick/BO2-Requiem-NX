// Bots in Party modes (Gun Game, One in the Chamber, Sticks & Stones, Sharpshooter)
// BO2 Requiem NX: /switch/t6game/scripts/mp/party_bots.gsc
//
// The stock _bot.gsc only spawns bots in dm, tdm, ctf, dem, dom, koth, hq and conf.
// This script replaces bot_gametype_allowed() so it also accepts gun, oic, sas and shrp.
// The lobby disables "Setup Bots" in these modes, so the count/difficulty saved the
// last time you set up bots in a regular mode is used; if the count is zero,
// party_bots_default_count() is used instead.

main()
{
    replacefunc( maps\mp\bots\_bot::bot_gametype_allowed, ::party_bot_gametype_allowed );
}

// Enemy count used in Party modes when bot_enemies is 0. Edit to taste.
party_bots_default_count()
{
    return 5;
}

party_bot_gametype_allowed()
{
    level.bot_gametype = maps\mp\bots\_bot::gametype_void;

    switch ( level.gametype )
    {
        case "dm":
        case "tdm":
            return true;
        case "ctf":
            level.bot_gametype = maps\mp\bots\_bot_ctf::bot_ctf_think;
            return true;
        case "dem":
            level.bot_gametype = maps\mp\bots\_bot_dem::bot_dem_think;
            return true;
        case "dom":
            level.bot_gametype = maps\mp\bots\_bot_dom::bot_dom_think;
            return true;
        case "koth":
            level.bot_gametype = maps\mp\bots\_bot_koth::bot_koth_think;
            return true;
        case "hq":
            level.bot_gametype = maps\mp\bots\_bot_hq::bot_hq_think;
            return true;
        case "conf":
            level.bot_gametype = maps\mp\bots\_bot_conf::bot_conf_think;
            return true;
        case "gun":
        case "oic":
        case "sas":
        case "shrp":
            if ( getdvarint( #"bot_enemies" ) <= 0 )
                setdvar( "bot_enemies", "" + party_bots_default_count() );

            return true;
    }

    return false;
}
