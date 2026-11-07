// Fix for bot_choose_class() in maps/mp/bots/_bot.gsc
// BO2 Requiem NX: /switch/t6game/scripts/mp/bot_class_fix.gsc
//
// When a bot is killed by an aircraft killstreak (UAV, helicopters...) it looks for a class
// with a launcher, but the stock code passes the position in its list of class names
// (0, 1, 2...) to getloadoutweapon()/getloadoutperks() as if it were the class number. The
// list grows while it is walked, so the positions go past the last class and the engine logs
// "Invalid unlockable item" for each one (a burst of ~10 lines when a killstreak goes up).
// This version passes the real class number (custom0-4 -> 0-4, default classes -> 10-14)
// and only walks the classes that were in the list to begin with.

main()
{
    replacefunc( maps\mp\bots\_bot::bot_choose_class, ::bot_choose_class_fixed );
}

bot_class_num( name )
{
    if ( issubstr( name, "custom" ) )
        return int( getsubstr( name, 6 ) );

    if ( isdefined( level.classmap[name] ) && isdefined( level.classtoclassnum[level.classmap[name]] ) )
        return level.classtoclassnum[level.classmap[name]];

    return undefined;
}

bot_choose_class_fixed()
{
    bot_classes = maps\mp\bots\_bot::bot_build_classes();

    if ( ( self maps\mp\bots\_bot_combat::threat_requires_rocket( self.bot.attacker ) || self maps\mp\bots\_bot_combat::threat_is_qrdrone( self.bot.attacker ) ) && !maps\mp\bots\_bot_combat::threat_is_warthog( self.bot.attacker ) )
    {
        if ( randomint( 100 ) < 75 )
        {
            bot_classes[bot_classes.size] = "class_smg";
            bot_classes[bot_classes.size] = "class_cqb";
            bot_classes[bot_classes.size] = "class_assault";
            bot_classes[bot_classes.size] = "class_lmg";
            bot_classes[bot_classes.size] = "class_sniper";
        }

        count = bot_classes.size;

        for ( i = 0; i < count; i++ )
        {
            num = bot_class_num( bot_classes[i] );

            if ( !isdefined( num ) )
                continue;

            sidearm = self getloadoutweapon( num, "secondary" );

            if ( sidearm == "fhj18_mp" )
            {
                self notify( "menuresponse", "changeclass", bot_classes[i] );
                return;
            }
            else if ( sidearm == "smaw_mp" )
            {
                bot_classes[bot_classes.size] = bot_classes[i];
                bot_classes[bot_classes.size] = bot_classes[i];
                bot_classes[bot_classes.size] = bot_classes[i];
            }
        }
    }

    if ( maps\mp\bots\_bot_combat::threat_requires_rocket( self.bot.attacker ) || maps\mp\bots\_bot_combat::threat_is_warthog( self.bot.attacker ) )
    {
        count = bot_classes.size;

        for ( i = 0; i < count; i++ )
        {
            num = bot_class_num( bot_classes[i] );

            if ( !isdefined( num ) )
                continue;

            perks = self getloadoutperks( num );

            foreach ( perk in perks )
            {
                if ( perk == "specialty_nottargetedbyairsupport" )
                {
                    bot_classes[bot_classes.size] = bot_classes[i];
                    bot_classes[bot_classes.size] = bot_classes[i];
                    bot_classes[bot_classes.size] = bot_classes[i];
                }
            }
        }
    }

    self notify( "menuresponse", "changeclass", random( bot_classes ) );
}
