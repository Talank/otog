# This script mostly does it job, still need to properly manage on some versions, and input orders, output orders

script_dir="/scratch/tbaral/icse25_runtime/run_on_future_versions/scripts"
MVNINSTALLOPTIONS="-Djacoco.skip=true -Dmaven.javadoc.skip=true -Drat.skip=true -Dmaven.test.failure.ignore=true -fn -Dlicense.skip=true -Dcheckstyle.skip -Denforcer.skip=true -Dspotbugs.skip=true -Dfindbugs.skip=true -DfailIfNoTests=false -Ddependency-check.skip=true"

create_mvn_instance() {
    module_id=$1
    version_number=$2
    # remove the maven instance if it already exists
    if [ -d $mvn_instance_base_dir/$version_number/$module_id ]; then
        echo "Removing existing maven instance for $version_number/$module_id"
        echo "rm -rf $mvn_instance_base_dir/$version_number/$module_id"
        rm -rf $mvn_instance_base_dir/$version_number/$module_id
    fi

    echo "Creating maven instance for $version_number/$module_id"
    mkdir -p $mvn_instance_base_dir/$version_number/$module_id
    cp $apache_zip_dir $mvn_instance_base_dir/$version_number/$module_id/
    unzip $mvn_instance_base_dir/$version_number/$module_id/apache-maven-3.6.3-bin.zip -d $mvn_instance_base_dir/$version_number/$module_id/
    mv $mvn_instance_base_dir/$version_number/$module_id/apache-maven-3.6.3 $mvn_instance_base_dir/$version_number/$module_id/maven
    
    export M2_HOME=$mvn_instance_base_dir/$version_number/$module_id/maven
    export PATH=$PATH:$M2_HOME/bin
    export JAVA_HOME="$HOME/.sdkman/candidates/java/8.0.392-amzn"
    export PATH=$PATH:$JAVA_HOME/bin
}

setup_custom_surefire_on_mvn_instance() {
    echo "Setting up custom surefire on maven instance"
    git clone https://github.com/TestingResearchIllinois/maven-surefire.git $mvn_instance_base_dir/$version_number/$module_id/maven-surefire
    cd $mvn_instance_base_dir/$version_number/$module_id/maven-surefire
    mvn install -DskipTests -Drat.skip -Denforcer.skip -Dcheckstyle.skip
    cp $mvn_instance_base_dir/$version_number/$module_id/maven-surefire/surefire-changing-maven-extension/target/surefire-changing-maven-extension-1.0-SNAPSHOT.jar $mvn_instance_base_dir/$version_number/$module_id/maven/lib/ext/
    cd -

    ls $mvn_instance_base_dir/$version_number/$module_id/maven/lib/ext/
}

inject_plugin_management() {
  local pom_file="$1"
  if [[ ! -f "$pom_file" ]]; then
    echo "Error: File '$pom_file' not found." >&2
    return 1
  fi

  # Create a backup of the original pom.xml
  cp "$pom_file" "${pom_file}.bak"
  echo "Backup created at ${pom_file}.bak"

  # Use sed to insert the pluginManagement block before the closing </build> tag.
  # Note: On macOS you might need to change `sed -i` to `sed -i ''`.
  sed -i "/<\/build>/i\\
<pluginManagement>\\
  <plugins>\\
    <plugin>\\
      <groupId>org.apache.felix</groupId>\\
      <artifactId>maven-bundle-plugin</artifactId>\\
      <version>\2.5.0</version>\\
    </plugin>\\
  </plugins>\\
</pluginManagement>" "$pom_file"

  echo "Injected pluginManagement block into $pom_file"
}

fix_project_for_init_run() {
    project_path=$1
    module=$2
    module_path=$project_path/$module
    sha_to_checkout=$3
    project_name=$4

    echo "Fixing project for initial run"
    echo "project path: $project_path"
    echo "project name: $project_name"
    echo "Module path: $module_path"
    # exit 0

    cd $project_path
    # git checkout $sha_to_checkout remove every unstagedchanges or whatever.. make sure the project is in the state of the commit_n_25
    git stash save "stash before checkout"
    git checkout $sha_to_checkout

    echo "Running the sed"
    whereis sed

    if [[ "$project_name" == "openpojo" ]]; then
        echo "Openpojo project, running the sed command to change the CredentialsRandomGenerator.java file"
        sed -i '70s/.*/return null;/' src/main/java/com/openpojo/random/generator/security/CredentialsRandomGenerator.java

    elif [[ "$project_name" == "Achilles" ]]; then
        echo "Achilles project, changing the version of the maven-surefire-plugin"
        ls | grep pom.xml
        sed -i 's~http://repo1.maven.org/maven2~https://repo1.maven.org/maven2~g' pom.xml
        find . -name "pom.xml" -type f -exec sed -i 's/6.0.1-SNAPSHOT/6.0.1/g' {} +
        inject_plugin_management pom.xml

    elif [[ "$project_name" == "spring-data-envers" ]]; then
        echo "Spring-data-envers project, changing the version of the spring-data-releasetrain"
        sed -i 's~2.2.0.BUILD-SNAPSHOT~2.2.0.RELEASE~g' pom.xml

    elif [[ "$project_name" == "dubbo" ]]; then
        # change 2.7.0-SNAPSHOT to 2.7.0 in the pom.xml

        echo "Dubbo project, changing the version of the dubbo-parent"
        # find . -name "pom.xml" -type f -exec sed -i 's/2.6.2-SNAPSHOT/2.6.2/g' {} +
        find . -name "pom.xml" -type f -exec sed -i 's/2.7.0-SNAPSHOT/2.7.0/g' {} +


    elif [[ "$project_name" == "jhipster-registry" ]]; then
        echo "Jhipster-registry project, changing the version of the spring-cloud-netflix"
        find . -name "pom.xml" -type f -exec sed -i 's/2.0.0-20180302.125522-36/2.0.0/g' {} +

    elif [[ "$project_name" == "hadoop" ]]; then
        echo "fixing hadoop, changing the version of the apacheds-server-integ to 2.0.0.AM27 from 2.0.0-M21"
        # find . -name "pom.xml" -type f -exec sed -i 's/2.0.0-M21/2.0.0.AM27/g' {} +
        # sudo apt-get install autoconf automake libtool curl make g++ unzip -y --allow-unauthenticated
        wget -nv https://github.com/protocolbuffers/protobuf/releases/download/v2.5.0/protobuf-2.5.0.tar.gz
        tar -zxvf protobuf-2.5.0.tar.gz
        cd protobuf-2.5.0 || continue # Continue if directory doesn't exist
        # ./configure
        ./configure --prefix=/scratch/tbaral/icse25_runtime/run_on_future_versions/usr/local
        make -j15
        make install
        ldconfig
        cd ..

        cd $module_path
        sed -i 's/3.3.0-SNAPSHOT/3.3.0/g' pom.xml
    fi

    cd -
}


# run maven install command simply on the module
run_init_maven_test() {
    project_path=$1
    module=$2
    module_path=$project_path/$module

    mkdir -p $init_runs_base_dir

    echo "Running maven install on $project_path"
    cd $project_path
    mvn clean install -pl $module -am $MVNINSTALLOPTIONS -DskipTests
    cd -

    echo "Running maven install on $module_path"
    echo "And saving the logs in $init_runs_base_dir/maven_log.log"
    cd $module_path
    rm -rf $init_runs_base_dir/surefire-reports
    mkdir -p $init_runs_base_dir/surefire-reports
    mvn test $MVNINSTALLOPTIONS 2>&1 | tee $init_runs_base_dir/maven_log.log
    cp $module_path/target/surefire-reports/* $init_runs_base_dir/surefire-reports/
    cd -
}


run_maven_command() {
    local order_to_run=$1
    local save_order_dir=$2

    module_path=$3
    num_of_executions=3

    # if order_to_run is not a file, then return
    if [ ! -f $order_to_run ]; then
        echo "Order file not found: $order_to_run"
        return
    fi

    cd $module_path

    rm -rf target

    mkdir -p $save_order_dir

    run_trials=0

    for iteratiion in $(seq 1 $num_of_executions); do
        # if [ $iteratiion -eq $num_of_executions ]; then
        #     break
        # fi
        mkdir -p $save_order_dir/$iteratiion
        while true; do
            rm -rf $save_order_dir/$iteratiion/*
            echo "Running test order: $order_to_run"
            mvn test -Dtest=$order_to_run -Dsurefire.runOrder=testorder $MVNINSTALLOPTIONS 2>&1 | tee $save_order_dir/$iteratiion.log
            cp $module_path/target/surefire-reports/* $save_order_dir/$iteratiion/
            # if [ "$(ls -A $save_order_dir/1)" ]; then if there are some xml files in the surefire-reports directory then break
            if [ "$(ls -A $save_order_dir/1 | grep .xml)" ]; then
                break
            fi
            three_try=0
            while [ $three_try -lt 3 ]; do
                cp $module_path/target/surefire-reports/* $save_order_dir/$iteratiion/
                if [ "$(ls -A $save_order_dir/$iteratiion | grep .xml)" ]; then
                    break
                fi
                three_try=$((three_try+1))
            done
            if [ "$(ls -A $save_order_dir/$iteratiion | grep .xml)" ]; then
                break
            fi
            run_trials=$((run_trials+1))
            if [ $run_trials -eq 3 ]; then
                break
            fi
        done
    done

    cd -
}

clone_projects(){
    url=$1
    sha_to_checkout=$2
    projects_dir=$3

    echo "Cloning projects to $projects_dir"

    if [ -d $projects_dir ]; then
        cd $projects_dir
        git stash save "stash before checkout"
        git checkout $sha_to_checkout
        cd -
        return
    fi

    mkdir -p $projects_dir
    git clone $url $projects_dir
    cd $projects_dir/v$version_number/$module_id
    git checkout $sha_to_checkout
    cd -
    # exit 0
}


# future_versions=(1 25 50 75 100)
# module_ids_we_are_considering=(1 12 14 24 27 28 30 31 37)

# future_versions=(1)
# module_ids_we_are_considering=(1)
version=$1
module_id=$2

postfixes=("_naive" "_ml" "_greedy" "_z3")
test_orders_base_dir="$script_dir/../test_orders"

# for version in "${future_versions[@]}"
# do
#     for module_id in "${module_ids_we_are_considering[@]}"
#     do
        # Declare variables
        # module_id=$1
        # version_number=$2

referenced_sheet="$script_dir/../referenced_sheets/future_versions.csv"
project_path="$script_dir/../projects/vf$version/$module_id"
init_runs_base_dir="$script_dir/../runs_nf$version/init_runs/$module_id"
init_test_list="$script_dir/../test_list/vf$version/$module_id.txt"
runs_base_dir="$script_dir/../runs_nf$version/approaches_run/$module_id"
mvn_instance_base_dir="$script_dir/../mvn_instances"
apache_zip_dir="$script_dir/apache-maven-3.6.3-bin.zip"
json_summary_result_basepath="$script_dir/../json_summary_results_nf$version/$module_id.json"
final_test_orders_dir="$script_dir/../final_orders/nf$version"
always_use_this_test_orders="/scratch/tbaral/icse25_runtime/run_on_future_versions/test_orders/orders_to_use"

# make the dirs
mkdir -p $init_runs_base_dir
mkdir -p $runs_base_dir
mkdir -p $script_dir/../json_summary_results_nf$version
mkdir -p $script_dir/../test_list/vf$version/


while IFS=, read -r ID project_name module_name link v1 v25 v50 v75 v100; do
    if [ "$ID" == "$module_id" ]; then
        module_path="$project_path/$module_name"
        if [ "$version" == "1" ]; then
            sha_to_checkout=$v1
        elif [ "$version" == "25" ]; then
            sha_to_checkout=$v25
        elif [ "$version" == "50" ]; then
            sha_to_checkout=$v50
        elif [ "$version" == "75" ]; then
            sha_to_checkout=$v75
        elif [ "$version" == "100" ]; then
            sha_to_checkout=$v100
        fi
        module=$module_name
        break
    fi
done < $referenced_sheet

# if sha_to_checkout is empty then return
if [ -z "$sha_to_checkout" ]; then
    echo "Error: sha_to_checkout is empty"
    exit 1
fi

clone_projects $link $sha_to_checkout $project_path

create_mvn_instance $module_id $version
fix_project_for_init_run $project_path $module $sha_to_checkout $project_name
run_init_maven_test $project_path $module


cd $script_dir #this is the dir where i have the get_test_list.py and the runs/ dir consisting of the initial run log and initial run surefire reports
python3 get_test_list.py $init_runs_base_dir/surefire-reports/ $init_test_list #this might need checking. coz the init list is not being created although there are logs
cd $script_dir
setup_custom_surefire_on_mvn_instance

for postfix in "${postfixes[@]}"
do
    # order_file="$test_orders_base_dir/n$version/${module_id}$postfix.txt"

    postfix_without_underscore="${postfix//_/}"
    order_file_historical="$always_use_this_test_orders/${module_id}$postfix.txt"

    mkdir -p $final_test_orders_dir
    mkdir -p $runs_base_dir/$postfix_without_underscore

    python3 fix_order.py $order_file_historical $init_test_list $final_test_orders_dir/${module_id}_${postfix_without_underscore}.txt

    run_maven_command $final_test_orders_dir/${module_id}_${postfix_without_underscore}.txt $runs_base_dir/$postfix_without_underscore $module_path

    python3 get_runtime.py "$runs_base_dir/$postfix_without_underscore" "$final_test_orders_dir/${module_id}_${postfix_without_underscore}.txt" $json_summary_result_basepath $postfix_without_underscore
done
#     done
# done
