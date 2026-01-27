function addTokenToIndexedDB(){
    return new Promise((resolve)=>{
        const request = indexedDB.open('keyval-store', 1);
        request.onsuccess = function(event) {
            const db = event.target.result;
            const transaction = db.transaction(['keyval'], 'readwrite').objectStore("keyval");
            let action = transaction.get("pizzax::base");
            action.onsuccess = (event)=>{
                const data = event.target.result;
                const verKey = location.hostname + "/" + window.userAccount.id;
                console.log(data);
                if(data.accountInfos == undefined){
                    data.accountInfos = {};
                }
                if(data.accountTokens == undefined){
                    data.accountTokens = {};
                }
                data.accountInfos[verKey] = window.userAccount;
                data.accountTokens[verKey] = window.userAccount.token;
                const requestUpdate = transaction.put(data, "pizzax::base");
                requestUpdate.onsuccess = resolve;
                requestUpdate.onerror = resolve;
            };
            action.onerror = resolve;
        }
        request.onerror = resolve;
    })
}

(async ()=>{
    // Add to user preference
    if("preferences" in localStorage){
        let prefer = JSON.parse(localStorage.preferences);
        let alreadyThere = false;
        for(userDoc of prefer.preferences.accounts[0][1]){
            if(userDoc[1].username == window.userAccount.username){
                alreadyThere = true;
                break;
            }
        }
        if(!alreadyThere){
            prefer.preferences.accounts[0][1].push([
                location.hostname, {"id": window.userAccount.id, "username": window.userAccount.username}
            ]);
            localStorage.preferences = JSON.stringify(prefer);
            await addTokenToIndexedDB();
        }
    }
    location.assign("/");
})()