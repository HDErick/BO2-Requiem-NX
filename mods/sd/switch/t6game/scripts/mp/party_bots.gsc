// Bots nos modos Party (Gun Game, One in the Chamber, Sticks & Stones, Sharpshooter)
// BO2 Requiem NX: /switch/t6game/scripts/mp/party_bots.gsc
//
// O _bot.gsc original so cria bots em dm, tdm, ctf, dem, dom, koth, hq e conf.
// Este script troca bot_gametype_allowed() para aceitar tambem gun, oic, sas e shrp.
// Como o lobby desativa "Configurar Bots" nesses modos, usa a quantidade/dificuldade
// que ficou salva da ultima vez que voce configurou bots num modo normal; se estiver
// zerada, usa party_bots_default_count().

main()
{
    replacefunc( maps\mp\bots\_bot::bot_gametype_allowed, ::party_bot_gametype_allowed );
}

// Inimigos usados nos modos Party quando bot_enemies esta em 0. Edite se quiser.
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
