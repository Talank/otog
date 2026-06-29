module_id=$1

echo "RUNNING.. module_id: $module_id"

module_ids_we_are_considering=(1 12 14 22 24 25 27 28 29 30 31 37)

clone_projects_v0(){
    projects_dir=$1
    mkdir -p $projects_dir/v0
    ref_sheet="../referenced_sheets/module_ids.csv"
    while IFS=, read -r ID project_name module_name url sha; do
        # if ID == "ID" then skip
        if [ $ID == "ID" ]; then
            continue
        fi

        # if ID not equal to module_id then skip
        if [ $ID != $module_id ]; then
            continue
        fi

        # if [[ ! " ${module_ids_we_are_considering[@]} " =~ " $ID " ]]; then
        #     continue
        # fi
        
        git clone $url $projects_dir/v0/$ID
        repo_name=$(basename $url .git)
        cd $projects_dir/v0/$ID
        git checkout $sha
        cd -
        # bash run_multiple_orders.sh $ID
    done < $ref_sheet
}

projects_dir="../projects"
script_dir=$(pwd)
clone_projects_v0 $script_dir/$projects_dir

bash run_multiple_orders.sh $module_id
