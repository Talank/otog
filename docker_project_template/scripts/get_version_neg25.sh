script_dir=$(pwd)
projects_dir="$script_dir/../projects/v0"
ref_sheet="$script_dir/../referenced_sheets/module_ids.csv"
commit_n_25_sheet="$script_dir/../referenced_sheets/commit_n_25.csv"

# module_ids_we_are_considering=(1 12 14)
module_ids_we_are_considering=(1 12 14 22 24 25 27 28 29 30 31 37)

# write_header
echo "ID,project_name,module_name,url,sha,commit_n_25" > $commit_n_25_sheet

while IFS=, read -r ID project_name module_name url sha; do
    # if ID == "ID" then skip
    if [ $ID == "ID" ]; then
        continue
    fi
    if [[ ! " ${module_ids_we_are_considering[@]} " =~ " $ID " ]]; then
        continue
    fi

    cd $projects_dir/$ID
    commit_n_25=$(git log --pretty=oneline | head -n 26 | tail -n 1 | cut -d' ' -f1)
    echo "$ID,$project_name,$module_name,$url,$sha,$commit_n_25" >> $commit_n_25_sheet
    cd -

done < $ref_sheet
