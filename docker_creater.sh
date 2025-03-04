template="/home/tbaral/research/otog_icse/docker_project_template"

# module_ids_we_are_considering=(1 12 14 22 24 25 27 28 29 30 31 37)
module_ids_we_are_considering=(1 12)

for i in {1..40}
do
    if [[ ! " ${module_ids_we_are_considering[@]} " =~ " $i " ]]; then
        continue
    fi
    cp -r $template /home/tbaral/research/otog_icse/docker_module_$i
    # replace <ID> with $i
    sed -i "s/<ID>/$i/g" /home/tbaral/research/otog_icse/docker_module_$i/Dockerfile
done