const fs = require("fs");
const { graphql } = require("@octokit/graphql");

const token = process.env.GITHUB_TOKEN;
const username = process.env.USERNAME;

(async () => {

const client = graphql.defaults({
headers:{
authorization:`token ${token}`
}
});

const data = await client(`
query($login:String!){
user(login:$login){

contributionsCollection{

contributionCalendar{

weeks{

contributionDays{

date

contributionCount

}
}
}
}
}
}
`,{
login:username
});

const days =
data.user.contributionsCollection
.contributionCalendar
.weeks
.flatMap(w=>w.contributionDays);

let current=0;
let longest=0;
let running=0;

for(const d of days){

if(d.contributionCount>0){

running++;

}else{

running=0;

}

if(running>longest)
longest=running;

}

for(let i=days.length-1;i>=0;i--){

if(days[i].contributionCount>0){

current++;

}else{

break;

}

}

const svg=`

<svg xmlns="http://www.w3.org/2000/svg"
width="900"
height="180">

<rect
width="100%"
height="100%"
rx="18"
fill="#0f172a"/>

<text
x="40"
y="60"
fill="#ffffff"
font-size="34"
font-family="Segoe UI"
font-weight="700">

🔥 GitHub Streak

</text>

<text
x="40"
y="110"
fill="#22D3EE"
font-size="26"
font-family="Segoe UI">

Current Streak

</text>

<text
x="330"
y="110"
fill="#6C63FF"
font-size="38"
font-family="Segoe UI"
font-weight="700">

${current} days

</text>

<text
x="40"
y="155"
fill="#22D3EE"
font-size="26">

Longest Streak

</text>

<text
x="330"
y="155"
fill="#6C63FF"
font-size="38"
font-weight="700">

${longest} days

</text>

</svg>

`;

fs.mkdirSync("assets",{recursive:true});

fs.writeFileSync("assets/github-streak.svg",svg);

})();
