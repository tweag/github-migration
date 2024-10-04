#!/usr/bin/env bash
# getSourcegraphOddballs.sh
#
# Retrieve all matches for github.example.com/[non-user-non-org-non-api] from Sourcegraph
#
# Requires Sourcegraph CLI, install on Mac via Homebrew with:
#
#   brew install sourcegraph/src-cli/src-cli


# Set bash unofficial strict mode http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail

# Set DEBUG to true for enhanced debugging: run prefixed with "DEBUG=true"
${DEBUG:-false} && set -vx
# Credit to https://stackoverflow.com/a/17805088
# and http://wiki.bash-hackers.org/scripting/debuggingtips
export PS4='+(${BASH_SOURCE}:${LINENO}): ${FUNCNAME[0]:+${FUNCNAME[0]}(): }'

# Credit to http://stackoverflow.com/a/246128/424301
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$DIR/.."
SCRIPTS_DIR="$BASE_DIR/scripts"
DATA_DIR="$DIR/../data"
export BASE_DIR SCRIPTS_DIR

CALL_APIS=${1:-true}

if "$CALL_APIS"; then
  export SRC_ACCESS_TOKEN=${SRC_ACCESS_TOKEN:?You must specify a SRC_ACCESS_TOKEN environment variable}
fi

export SRC_ENDPOINT="https://sourcegraph.example.com/"
RAW_RESULTS="$DATA_DIR/sourcegraph-github.example.com-oddballs.json"
ODDBALL_RESULTS="$DATA_DIR/sourcegraph-github.example.com-oddballs-content.txt"
UNIQUE_RESULTS="$DATA_DIR/sourcegraph-github.example.com-oddballs-unique.txt"
UNIQUE_REGEX="$DATA_DIR/sourcegraph-github.example.com-oddballs-unique-regex.txt"

RESERVED='\b(about|access|account|accounts|activate|activities|activity|ad|add|address|adm|admin|administration|administrator|ads|adult|advertising|affiliate|affiliates|ajax|all|alpha|analysis|analytics|android|anon|anonymous|app|apps|archive|archives|article|asct|asset|atom|auth|authentication|avatar|backup|balancer-manager|banner|banners|beta|billing|bin|blog|blogs|board|book|bookmark|bot|bots|bug|business|cache|cadastro|calendar|call|campaign|cancel|captcha|career|careers|cart|categories|category|cgi|cgi-bin|changelog|chat|check|checking|checkout|client|cliente|clients|code|codereview|comercial|comment|comments|communities|community|company|compare|compras|config|configuration|connect|contact|contact-us|contact_us|contactus|contest|contribute|corp|create|css|dashboard|data|db|default|delete|demo|design|designer|destroy|dev|devel|developer|developers|diagram|diary|dict|dictionary|die|dir|direct_messages|directory|dist|doc|docs|documentation|domain|download|downloads|ecommerce|edit|editor|edu|education|email|employment|empty|end|enterprise|entries|entry|error|errors|eval|event|everyone|exit|explore|facebook|faq|favorite|favorites|feature|features|feed|feedback|feeds|file|files|first|flash|fleet|fleets|flog|follow|followers|following|forgot|form|forum|forums|founder|free|friend|friends|ftp|gadget|gadgets|game|games|get|ghost|gift|gifts|gist|github|graph|group|groups|guest|guests|help|home|homepage|host|hosting|hostmaster|hostname|howto|hpg|html|http|httpd|https|i|iamges|icon|icons|id|idea|ideas|image|images|imap|img|index|indice|info|information|inquiry|instagram|intranet|invitations|invite|ipad|iphone|irc|is|issue|issues|it|item|items|java|javascript|job|jobs|join|js|json|jump|knowledgebase|language|languages|last|ldap-status|legal|license|link|links|linux|list|lists|log|log-in|log-out|log_in|log_out|login|logout|logs|m|mac|mail|mail1|mail2|mail3|mail4|mail5|mailer|mailing|maintenance|manager|manual|map|maps|marketing|master|me|media|member|members|message|messages|messenger|microblog|microblogs|mine|mis|mob|mobile|movie|movies|mp3|msg|msn|music|musicas|mx|my|mysql|name|named|nan|navi|navigation|net|network|new|news|newsletter|nick|nickname|notes|noticias|notification|notifications|notify|ns|ns1|ns10|ns2|ns3|ns4|ns5|ns6|ns7|ns8|ns9|null|oauth|oauth_clients|offer|offers|official|old|online|openid|operator|order|orders|organization|organizations|overview|owner|owners|page|pager|pages|panel|password|payment|perl|phone|photo|photoalbum|photos|php|phpmyadmin|phppgadmin|phpredisadmin|pic|pics|ping|plan|plans|plugin|plugins|policy|pop|pop3|popular|portal|post|postfix|postmaster|posts|pr|premium|press|price|pricing|privacy|privacy-policy|privacy_policy|privacypolicy|private|product|products|profile|project|projects|promo|pub|public|purpose|put|python|query|random|ranking|read|readme|recent|recruit|recruitment|register|registration|release|remove|replies|report|reports|repositories|repository|req|request|requests|reset|roc|root|rss|ruby|rule|sag|sale|sales|sample|samples|save|school|script|scripts|search|security|self|send|server|server-info|server-status|service|services|session|sessions|setting|settings|setup|share|shop|show|sign-in|sign-up|sign_in|sign_up|signin|signout|signup|site|sitemap|sites|smartphone|smtp|soporte|source|spec|special|sql|src|ssh|ssl|ssladmin|ssladministrator|sslwebmaster|staff|stage|start|stat|state|static|stats|status|store|stores|stories|style|styleguide|stylesheet|stylesheets|subdomain|subscribe|subscriptions|suporte|support|svn|swf|sys|sysadmin|sysadministrator|system|tablet|tablets|tag|talk|task|tasks|team|teams|tech|telnet|term|terms|terms-of-service|terms_of_service|termsofservice|test|test1|test2|test3|teste|testing|tests|theme|themes|thread|threads|tmp|todo|tool|tools|top|topic|topics|tos|tour|translations|trends|tutorial|tux|tv|twitter|undef|unfollow|unsubscribe|update|upload|uploads|url|usage|user|username|users|usuario|vendas|ver|version|video|videos|visitor|watch|weather|web|webhook|webhooks|webmail|webmaster|website|websites|welcome|widget|widgets|wiki|win|windows|word|work|works|workshop|ww|wws|www|www1|www2|www3|www4|www5|www6|www7|wwws|wwww|xfn|xml|xmpp|xpg|xxx|yaml|year|yml|you|yourdomain|yourname|yoursite|yourusername)\b'

if $CALL_APIS; then
	src search -json \
		"github.example.com[:/] $RESERVED select:content count:all" \
		> "$RAW_RESULTS"
fi


jq  --raw-output '.Results[].file.content' "$RAW_RESULTS" \
        | sed -e '
		s/^.*http/http/;
		s/[)>"? '"'"'].*$//g;
		' \
        | grep https://github.example.com \
        | sort \
        > "$ODDBALL_RESULTS"


 cut -d/ -f4 "$ODDBALL_RESULTS" \
        | grep -E "$RESERVED" \
	| uniq -c \
        > "$UNIQUE_RESULTS"

cut -c6- "$UNIQUE_RESULTS" \
	| tr '\n' '|' \
        | sed -e 's/|$//' \
        > "$UNIQUE_REGEX"

